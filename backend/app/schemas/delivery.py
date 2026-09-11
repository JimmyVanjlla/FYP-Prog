from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DeliveryScheduleCreate(BaseModel):
    po_id: int
    scheduled_date: date


class DeliveryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: int
    ingredient_id: int
    expected_quantity: Decimal
    received_quantity: Decimal | None


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_id: int
    po_id: int
    scheduled_date: date
    status: str
    received_by: int | None


class DeliveryDiscrepancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    discrepancy_id: int
    delivery_id: int
    ingredient_id: int
    issue_type: str
    return_required: bool
    status: str


class ReceiptConfirmation(BaseModel):
    # Maps DeliveryItem.item_id -> received quantity. FR10.5 — negative
    # values are rejected below the endpoint via the service's explicit
    # check rather than ge=0 here, so the "negative" case surfaces as a
    # clean validation error message rather than FastAPI's generic one.
    received_quantities: dict[int, Decimal] = Field(min_length=1)


class ReceiptConfirmationResult(BaseModel):
    delivery: DeliveryOut
    discrepancies: list[DeliveryDiscrepancyOut]
