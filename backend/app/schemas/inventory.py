from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngredientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    unit: str = Field(min_length=1, max_length=20)
    current_stock: Decimal = Field(default=Decimal("0"), ge=0)
    low_stock_threshold: Decimal | None = Field(default=None, ge=0)


class IngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingredient_id: int
    name: str
    unit: str
    current_stock: Decimal
    low_stock_threshold: Decimal | None
    is_low_stock: bool = False  # computed — see routers/inventory.py


class ThresholdUpdate(BaseModel):
    # None clears the override and falls back to the system default (FR3.3).
    low_stock_threshold: Decimal | None = Field(default=None, ge=0)


class StockAdjustmentCreate(BaseModel):
    """FR3.4 / FR3.6 — adjusted_quantity is signed (positive to add stock
    back, e.g. correcting a miscount, negative to remove it, e.g.
    spillage/spoilage); zero is meaningless so it's rejected too."""

    ingredient_id: int
    adjusted_quantity: Decimal
    reason_category: str = Field(min_length=1, max_length=20)
    note: str | None = None

    @field_validator("adjusted_quantity")
    @classmethod
    def _adjusted_quantity_not_zero(cls, v: Decimal) -> Decimal:
        # Pydantic v2 has no `ne=` Field constraint (it's silently accepted
        # as unused metadata, not enforced) — a zero adjustment is
        # meaningless, so reject it explicitly here instead.
        if v == 0:
            raise ValueError("adjusted_quantity cannot be zero.")
        return v


class StockAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    adjustment_id: int
    ingredient_id: int
    staff_id: int
    adjusted_quantity: Decimal
    reason_category: str
    note: str | None
    timestamp: datetime


class StockBatchCreate(BaseModel):
    ingredient_id: int
    quantity: Decimal = Field(gt=0)
    received_date: date
    expiry_date: date


class StockBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    ingredient_id: int
    quantity: Decimal
    received_date: date
    expiry_date: date
    status: str


class RestockingRequestCreate(BaseModel):
    ingredient_id: int
    quantity: Decimal = Field(gt=0)
    urgency: bool = False


class RestockingRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: int
    ingredient_id: int
    requested_by: int
    quantity: Decimal
    urgency: bool
    status: str


class RestockingRequestStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=20)
