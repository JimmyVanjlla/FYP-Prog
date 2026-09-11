"""
Module 10: Delivery Management business logic. FR10.1-FR10.5.

Checklist items A1/A2/A3: the delivery lifecycle is a genuine two-step
process, not one. UC-DM-02 (Delivery/Logistics Staff confirms receipt) and
UC-IM-01 (Inventory Staff separately verifies against stock records
*before* stock is actually updated) are different use cases with
different actors — confirm_receipt below never touches
Ingredient.current_stock; only verify_delivery does, and only once the PO
is in the "delivered" state (not "discrepancy_flagged"). PurchaseOrder and
Delivery share one status vocabulary (UC-PS-05 lists the exact same
lifecycle for a PO's status once it's past approval), kept in sync by
_sync_po_status.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.delivery import Delivery, DeliveryDiscrepancy, DeliveryItem
from app.models.inventory import Ingredient
from app.models.procurement import PurchaseOrder, PurchaseOrderItem

# How far a received quantity can deviate from expected before it's routed
# to the discrepancy flow instead of accepted as a standard receipt
# (FR10.5) — Ch4's data dictionary doesn't name this in SystemConfig, so
# it's a module-local constant rather than misusing an unrelated threshold
# (e.g. prep_deviation_threshold, which is Module 5's).
DEVIATION_THRESHOLD_PCT = Decimal("10.00")

# UC-DM-04's exact lifecycle. Also used as PurchaseOrder.status once a PO
# moves past approval (UC-PS-05).
DELIVERY_STATUSES = (
    "awaiting_delivery",
    "in_transit",
    "delivered",
    "discrepancy_flagged",
    "return_pending",
    "return_resolved",
)
# Statuses a Delivery/Logistics Staff member can set manually via
# update_delivery_status (UC-DM-04) — "delivered" and "discrepancy_flagged"
# are only ever reached through confirm_receipt's own logic (UC-DM-02),
# not set directly, since they depend on comparing received vs expected
# quantities.
MANUALLY_SETTABLE_STATUSES = ("awaiting_delivery", "in_transit", "return_pending", "return_resolved")


class NotFoundError(Exception):
    pass


class NegativeReceivedQuantityError(Exception):
    """FR10.5."""


class InvalidStatusError(Exception):
    """UC-DM-04 — not a real lifecycle value, or not one settable manually."""


class DiscrepancyMustBeResolvedFirstError(Exception):
    """UC-IM-01 Alt Flow 3a / UC-DM-04 Alt Flow 2a."""


def schedule_delivery(db: Session, *, po_id: int, scheduled_date: date) -> Delivery:
    """FR10.1 — one delivery per purchase order, seeded with expected
    quantities from the PO's line items."""
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise NotFoundError

    delivery = Delivery(po_id=po_id, scheduled_date=scheduled_date, status="awaiting_delivery")
    db.add(delivery)
    db.flush()

    po_items = db.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po_id)).all()
    for po_item in po_items:
        db.add(
            DeliveryItem(
                delivery_id=delivery.delivery_id,
                ingredient_id=po_item.ingredient_id,
                expected_quantity=po_item.quantity,
            )
        )

    po.status = "awaiting_delivery"
    db.commit()
    db.refresh(delivery)
    return delivery


def list_deliveries(db: Session, *, status: str | None = None) -> list[Delivery]:
    stmt = select(Delivery).order_by(Delivery.scheduled_date.desc())
    if status is not None:
        stmt = stmt.where(Delivery.status == status)
    return list(db.scalars(stmt))


def list_delivery_items(db: Session, delivery_id: int) -> list[DeliveryItem]:
    """FR10.2 — without this, confirm_receipt's {item_id: quantity} map
    is uncallable: there was no way for Delivery/Logistics Staff to ever
    discover which item_ids exist or what quantity was expected for each."""
    if db.get(Delivery, delivery_id) is None:
        raise NotFoundError
    return list(
        db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id))
    )


def _sync_po_status(db: Session, delivery: Delivery, new_status: str) -> None:
    """UC-PS-05 — a PO's status tracks the exact same delivery-lifecycle
    values once it has a delivery. Centralised here so every place that
    changes Delivery.status changes PurchaseOrder.status the same way."""
    delivery.status = new_status
    po = db.get(PurchaseOrder, delivery.po_id)
    if po is not None:
        po.status = new_status


def confirm_receipt(
    db: Session, *, delivery_id: int, received_by: int, received_quantities: dict[int, Decimal]
) -> tuple[Delivery, list[DeliveryDiscrepancy]]:
    """UC-DM-02 / FR10.2 / FR10.4 / FR10.5. received_quantities maps
    DeliveryItem.item_id -> received quantity.

    Deliberately does NOT touch Ingredient.current_stock — that's
    verify_delivery's job (UC-IM-01), a separate step for a separate
    actor (Inventory Staff). This only records what was physically
    received and decides, per FR10.5, whether that's within tolerance
    ("delivered") or needs the discrepancy flow ("discrepancy_flagged" /
    "return_pending" if a return is required — UC-DM-03 Alt Flow 3a)."""
    delivery = db.get(Delivery, delivery_id)
    if delivery is None:
        raise NotFoundError

    items = db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)).all()
    threshold = DEVIATION_THRESHOLD_PCT
    discrepancies: list[DeliveryDiscrepancy] = []

    for item in items:
        if item.item_id not in received_quantities:
            continue
        received = received_quantities[item.item_id]
        if received < 0:
            raise NegativeReceivedQuantityError

        item.received_quantity = received
        deviation_pct = (
            abs(received - item.expected_quantity) / item.expected_quantity * 100
            if item.expected_quantity
            else Decimal("0")
        )

        if deviation_pct > threshold:
            discrepancy = DeliveryDiscrepancy(
                delivery_id=delivery_id,
                ingredient_id=item.ingredient_id,
                issue_type="shortage" if received < item.expected_quantity else "wrong_item",
                return_required=received < item.expected_quantity,
                status="open",
            )
            db.add(discrepancy)
            discrepancies.append(discrepancy)

    if discrepancies:
        # UC-DM-03 Alt Flow 3a — a return-required discrepancy routes
        # straight to "return_pending"; a discrepancy that doesn't need a
        # physical return (e.g. wrong item, keep and credit) stays at
        # "discrepancy_flagged" until the Procurement Officer resolves it.
        new_status = "return_pending" if any(d.return_required for d in discrepancies) else "discrepancy_flagged"
    else:
        new_status = "delivered"

    _sync_po_status(db, delivery, new_status)
    delivery.received_by = received_by
    db.add(
        AuditLog(
            user_id=received_by,
            action=f"delivery_status:delivery={delivery_id}:status={new_status}",
        )
    )
    db.commit()
    db.refresh(delivery)
    for d in discrepancies:
        db.refresh(d)
    return delivery, discrepancies


def verify_delivery(db: Session, *, delivery_id: int, verified_by: int) -> Delivery:
    """UC-IM-01 — Inventory Staff verifies a delivery already confirmed by
    Delivery/Logistics Staff (UC-DM-02) against stock records, and *this*
    is what actually updates Ingredient.current_stock (FR3.1's "logged
    deliveries" update path). Alt Flow 3a: if the PO is
    "discrepancy_flagged" or "return_pending" rather than "delivered",
    verification is blocked until the discrepancy is resolved — incorrect
    quantities never get added to inventory."""
    delivery = db.get(Delivery, delivery_id)
    if delivery is None:
        raise NotFoundError
    if delivery.status != "delivered":
        raise DiscrepancyMustBeResolvedFirstError

    items = db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)).all()
    for item in items:
        if item.received_quantity is None:
            continue
        ingredient = db.get(Ingredient, item.ingredient_id)
        if ingredient is not None:
            ingredient.current_stock += item.received_quantity

    delivery.verified_by = verified_by
    delivery.verified_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(user_id=verified_by, action=f"delivery_verified:delivery={delivery_id}")
    )
    db.commit()
    db.refresh(delivery)
    return delivery


def update_delivery_status(db: Session, *, delivery_id: int, new_status: str, updated_by: int) -> Delivery:
    """UC-DM-04 — manual progression through the parts of the lifecycle
    confirm_receipt doesn't decide automatically (pre-receipt tracking,
    and the post-discrepancy return resolution). Alt Flow 2a: "Return
    Resolved" is blocked while any DeliveryDiscrepancy for this delivery
    is still open."""
    delivery = db.get(Delivery, delivery_id)
    if delivery is None:
        raise NotFoundError
    if new_status not in MANUALLY_SETTABLE_STATUSES:
        raise InvalidStatusError

    if new_status == "return_resolved":
        open_discrepancy = db.scalars(
            select(DeliveryDiscrepancy)
            .where(DeliveryDiscrepancy.delivery_id == delivery_id)
            .where(DeliveryDiscrepancy.status == "open")
        ).first()
        if open_discrepancy is not None:
            raise DiscrepancyMustBeResolvedFirstError

    _sync_po_status(db, delivery, new_status)
    db.add(
        AuditLog(
            user_id=updated_by,
            action=f"delivery_status:delivery={delivery_id}:status={new_status}",
        )
    )
    db.commit()
    db.refresh(delivery)
    return delivery


def list_delivery_discrepancies(db: Session, *, delivery_id: int | None = None) -> list[DeliveryDiscrepancy]:
    stmt = select(DeliveryDiscrepancy).order_by(DeliveryDiscrepancy.discrepancy_id.desc())
    if delivery_id is not None:
        stmt = stmt.where(DeliveryDiscrepancy.delivery_id == delivery_id)
    return list(db.scalars(stmt))


def resolve_discrepancy(db: Session, discrepancy_id: int) -> DeliveryDiscrepancy:
    discrepancy = db.get(DeliveryDiscrepancy, discrepancy_id)
    if discrepancy is None:
        raise NotFoundError
    discrepancy.status = "resolved"
    db.commit()
    db.refresh(discrepancy)
    return discrepancy
