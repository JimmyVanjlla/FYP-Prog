from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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
