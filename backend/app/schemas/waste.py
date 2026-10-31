from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WasteLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    waste_log_id: int
    source_type: str
    source_ref_id: int
    ingredient_id: int
    quantity_wasted: Decimal
    waste_cost: Decimal
    logged_at: datetime


class WasteReductionTrendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trend_id: int
    period_start: date
    period_end: date
    total_waste_cost: Decimal


class WasteTrendRequest(BaseModel):
    period_start: date
    period_end: date


class WasteLogCreate(BaseModel):
    """FR6.5 — a manually entered waste record. quantity_wasted must be
    positive; whether it's more than was prepared/delivered is checked
    against the source record in the service."""

    source_type: Literal["leftover", "expiry"]
    source_ref_id: int
    ingredient_id: int
    quantity_wasted: Decimal = Field(gt=0)
