from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.delivery import (
    DeliveryDiscrepancyOut,
    DeliveryItemOut,
    DeliveryOut,
    DeliveryScheduleCreate,
    DeliveryStatusUpdate,
    ReceiptConfirmation,
    ReceiptConfirmationResult,
)
from app.services import delivery as delivery_service

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

_DELIVERY_ROLES = (Role.DELIVERY_LOGISTICS_STAFF, Role.RESTAURANT_MANAGER)
# Scheduling a delivery follows straight on from creating its purchase
# order, so the Procurement Officer who raised the PO can also schedule
# the delivery — not just Delivery staff/the Manager.
_SCHEDULING_ROLES = (*_DELIVERY_ROLES, Role.PROCUREMENT_OFFICER)


@router.get("", response_model=list[DeliveryOut])
def list_deliveries(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[DeliveryOut]:
    """FR10.1 / FR10.4."""
    return delivery_service.list_deliveries(db, status=status_filter)


@router.post("", response_model=DeliveryOut, status_code=status.HTTP_201_CREATED)
def schedule_delivery(
    data: DeliveryScheduleCreate,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_SCHEDULING_ROLES)),
) -> DeliveryOut:
    """FR10.1."""
    try:
        return delivery_service.schedule_delivery(db, po_id=data.po_id, scheduled_date=data.scheduled_date)
    except delivery_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found.")


@router.get("/{delivery_id}/items", response_model=list[DeliveryItemOut])
def list_delivery_items(
    delivery_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[DeliveryItemOut]:
    """FR10.2 — what confirm-receipt actually needs callers to look up
    first: each item's item_id and expected_quantity."""
    try:
        return delivery_service.list_delivery_items(db, delivery_id)
    except delivery_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found.")


@router.post("/{delivery_id}/confirm-receipt", response_model=ReceiptConfirmationResult)
def confirm_receipt(
    delivery_id: int,
    data: ReceiptConfirmation,
    db: Session = Depends(get_db),
    staff: User = Depends(require_role(Role.DELIVERY_LOGISTICS_STAFF)),
) -> ReceiptConfirmationResult:
    """UC-DM-02 / FR10.2 / FR10.5. Records what was physically received
    and routes to the discrepancy flow if needed — does NOT update
    Ingredient.current_stock; see POST .../verify (UC-IM-01) for that
    separate step."""
    try:
        delivery, discrepancies = delivery_service.confirm_receipt(
            db,
            delivery_id=delivery_id,
            received_by=staff.user_id,
            received_quantities=data.received_quantities,
        )
    except delivery_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found.")
    except delivery_service.NegativeReceivedQuantityError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Received quantity cannot be negative.",
        )
    return ReceiptConfirmationResult(delivery=delivery, discrepancies=discrepancies)


@router.post("/{delivery_id}/verify", response_model=DeliveryOut)
def verify_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    staff: User = Depends(require_role(Role.INVENTORY_STAFF)),
) -> DeliveryOut:
    """UC-IM-01 — Inventory Staff's separate verification step; this is
    what actually updates Ingredient.current_stock, not confirm-receipt."""
    try:
        return delivery_service.verify_delivery(db, delivery_id=delivery_id, verified_by=staff.user_id)
    except delivery_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found.")
    except delivery_service.DiscrepancyMustBeResolvedFirstError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This delivery has an open discrepancy — resolve it before verifying stock.",
        )


@router.patch("/{delivery_id}/status", response_model=DeliveryOut)
def update_delivery_status(
    delivery_id: int,
    data: DeliveryStatusUpdate,
    db: Session = Depends(get_db),
    staff: User = Depends(require_role(*_DELIVERY_ROLES)),
) -> DeliveryOut:
    """UC-DM-04."""
    try:
        return delivery_service.update_delivery_status(
            db, delivery_id=delivery_id, new_status=data.status, updated_by=staff.user_id
        )
    except delivery_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found.")
    except delivery_service.InvalidStatusError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: {', '.join(delivery_service.MANUALLY_SETTABLE_STATUSES)}.",
        )
    except delivery_service.DiscrepancyMustBeResolvedFirstError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot mark as return_resolved while a discrepancy is still open.",
        )


@router.get("/discrepancies", response_model=list[DeliveryDiscrepancyOut])
def list_discrepancies(
    delivery_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[DeliveryDiscrepancyOut]:
    """FR10.3."""
    return delivery_service.list_delivery_discrepancies(db, delivery_id=delivery_id)


@router.post("/discrepancies/{discrepancy_id}/resolve", response_model=DeliveryDiscrepancyOut)
def resolve_discrepancy(
    discrepancy_id: int,
    db: Session = Depends(get_db),
    # UC-DM-04 Alt Flow 2a names the Procurement Officer as who closes a
    # discrepancy record specifically, alongside the roles that already
    # handle deliveries generally.
    _staff: User = Depends(require_role(*_DELIVERY_ROLES, Role.PROCUREMENT_OFFICER)),
) -> DeliveryDiscrepancyOut:
    """FR10.3."""
    try:
        return delivery_service.resolve_discrepancy(db, discrepancy_id)
    except delivery_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discrepancy not found.")
