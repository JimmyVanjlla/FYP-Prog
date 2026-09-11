from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PrepRecommendationRequest(BaseModel):
    """FR5.1 — asks the system to generate (or return the existing)
    recommendation for an item/meal-period/date, derived from the latest
    matching Forecast."""

    menu_item_id: int
    meal_period: str = Field(min_length=1, max_length=20)
    forecast_date: date


class PrepRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recommendation_id: int
    menu_item_id: int
    forecast_id: int
    meal_period: str
    recommended_quantity: Decimal


class PrepConfirmationCreate(BaseModel):
    confirmed_quantity: Decimal = Field(ge=0)
    # Required only when the deviation from the recommendation exceeds
    # SystemConfig.prep_deviation_threshold (FR5.5) — enforced in the
    # service layer, where the threshold and the recommendation both live.
    deviation_reason: str | None = None


class PrepConfirmationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    confirmation_id: int
    recommendation_id: int
    confirmed_quantity: Decimal
    deviation_reason: str | None
    staff_id: int


class LeftoverLogCreate(BaseModel):
    menu_item_id: int
    service_period_date: date
    prepared_quantity: Decimal = Field(gt=0)
    leftover_quantity: Decimal = Field(ge=0)
    leftover_level: str = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _leftover_cannot_exceed_prepared(self) -> "LeftoverLogCreate":
        # Same spirit as FR6.5's rule for waste logs — a leftover count
        # can't exceed how much was actually prepared for the service.
        if self.leftover_quantity > self.prepared_quantity:
            raise ValueError("leftover_quantity cannot exceed prepared_quantity.")
        return self


class LeftoverLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    menu_item_id: int
    service_period_date: date
    prepared_quantity: Decimal
    leftover_quantity: Decimal
    leftover_level: str
    staff_id: int


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_id: int
    type: str
    message: str
    status: str
    created_at: datetime
