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


class WasteWeekOut(BaseModel):
    period_start: date
    period_end: date
    leftover_cost: Decimal
    expiry_cost: Decimal
    total_cost: Decimal
    entries: int


class WasteTopIngredientOut(BaseModel):
    ingredient_id: int
    name: str
    unit: str
    quantity: Decimal
    cost: Decimal


class WasteTopDishOut(BaseModel):
    menu_item_id: int
    name: str
    cost: Decimal


class WasteSummaryOut(BaseModel):
    """Cost per week, and the biggest sources of waste over the last four weeks."""

    weeks: list[WasteWeekOut]
    top_ingredients: list[WasteTopIngredientOut]
    top_dishes: list[WasteTopDishOut]


class WastePredictionDishOut(BaseModel):
    menu_item_id: int
    menu_item_name: str
    forecast_portions: Decimal
    leftover_rate: Decimal
    expected_leftover_portions: Decimal
    expected_cost: Decimal


class WastePredictionOut(BaseModel):
    """Expected leftover waste for the coming days, from the forecast and the recent leftover rate."""

    period_start: date
    period_end: date
    total_cost: Decimal
    total_portions: Decimal
    dishes: list[WastePredictionDishOut]
