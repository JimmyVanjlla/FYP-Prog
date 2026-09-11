from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    """Historical order record — the raw input Algorithm 1 trains on
    (FR4.1). In later sprints this is populated automatically as customer
    orders are logged elsewhere; for now it's a direct entry point so the
    forecasting pipeline has real data to train against."""

    menu_item_id: int
    quantity: int = Field(gt=0)
    meal_period: str = Field(min_length=1, max_length=20)
    order_date: date


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    menu_item_id: int
    quantity: int
    meal_period: str
    order_date: date


class ForecastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    forecast_id: int
    menu_item_id: int
    meal_period: str
    forecast_date: date
    predicted_quantity: Decimal
    generated_at: datetime


class ForecastTrainingResult(BaseModel):
    forecasts_created: int
    skipped: list[dict]
    accuracy_records_created: int


class ForecastAccuracyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    accuracy_id: int
    forecast_id: int
    actual_quantity: Decimal
    accuracy_error: Decimal
