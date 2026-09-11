"""Module 10: Delivery Management business logic. FR10.1-FR10.5."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.delivery import Delivery, DeliveryDiscrepancy, DeliveryItem
from app.models.procurement import PurchaseOrder, PurchaseOrderItem
from app.models.inventory import Ingredient

# How far a received quantity can deviate from expected before it's routed
# to the discrepancy flow instead of accepted as a standard receipt
# (FR10.5) — Ch4's data dictionary doesn't name this in SystemConfig, so
# it's a module-local constant rather than misusing an unrelated threshold
# (e.g. prep_deviation_threshold, which is Module 5's).
DEVIATION_THRESHOLD_PCT = Decimal("10.00")


class NotFoundError(Exception):
    pass


class NegativeReceivedQuantityError(Exception):
    """FR10.5."""


def schedule_delivery(db: Session, *, po_id: int, scheduled_date: date) -> Delivery:
    """FR10.1 — one delivery per purchase order, seeded with expected
    quantities from the PO's line items."""
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise NotFoundError

    delivery = Delivery(po_id=po_id, scheduled_date=scheduled_date, status="scheduled")
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

    db.commit()
    db.refresh(delivery)
    return delivery


def list_deliveries(db: Session, *, status: str | None = None) -> list[Delivery]:
    stmt = select(Delivery).order_by(Delivery.scheduled_date.desc())
    if status is not None:
        stmt = stmt.where(Delivery.status == status)
    return list(db.scalars(stmt))


def confirm_receipt(
    db: Session, *, delivery_id: int, received_by: int, received_quantities: dict[int, Decimal]
) -> tuple[Delivery, list[DeliveryDiscrepancy]]:
    """FR10.2 / FR10.4 / FR10.5. received_quantities maps
    DeliveryItem.item_id -> received quantity. Confirmed quantities within
    the deviation threshold are added straight onto Ingredient.current_stock
    (FR3.1's "logged deliveries" update path); quantities outside the
    threshold are routed to a DeliveryDiscrepancy instead of a standard
    receipt (FR10.5), same as a negative quantity."""
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
        else:
            ingredient = db.get(Ingredient, item.ingredient_id)
            if ingredient is not None:
                ingredient.current_stock += received

    delivery.status = "received"
    delivery.received_by = received_by
    db.commit()
    db.refresh(delivery)
    for d in discrepancies:
        db.refresh(d)
    return delivery, discrepancies


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
