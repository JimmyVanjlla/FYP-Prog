from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.validators import require_letter


class PrepRecommendationRequest(BaseModel):
    """FR5.1 — asks the system to generate (or return the existing)
    recommendation for an item/meal-period/date, derived from the latest
    matching Forecast.

    UC-KO-01 Alt Flow 3a — when no forecast exists yet (e.g. a brand new
    menu item with no order history), manual_quantity is the fallback:
    Kitchen Staff enters a prep quantity directly instead of hitting a
    dead end. Omit it on the normal, forecast-backed path."""

    menu_item_id: int
    meal_period: str = Field(min_length=1, max_length=20)
    forecast_date: date
    manual_quantity: Decimal | None = Field(default=None, gt=0)


class PrepRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recommendation_id: int
    menu_item_id: int
    forecast_id: int | None
    meal_period: str
    forecast_date: date | None = None
    recommended_quantity: Decimal
    # Filled in by the router from the matching PrepConfirmation, if any.
    confirmed: bool = False
    confirmed_quantity: Decimal | None = None
    deviation_reason: str | None = None


class PrepConfirmationCreate(BaseModel):
    confirmed_quantity: Decimal = Field(ge=0)
    # Required only when the deviation from the recommendation exceeds
    # SystemConfig.prep_deviation_threshold (FR5.5) — enforced in the
    # service layer, where the threshold and the recommendation both live.
    deviation_reason: str | None = None

    @field_validator("deviation_reason")
    @classmethod
    def _needs_words(cls, value: str | None) -> str | None:
        # A blank reason means "none given" and is handled by the service;
        # anything typed must be words.
        if value is None or not value.strip():
            return value
        return require_letter(value)


class PrepConfirmationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    confirmation_id: int
    recommendation_id: int
    confirmed_quantity: Decimal
    deviation_reason: str | None
    staff_id: int


LEFTOVER_PERCENTS = (0, 25, 50, 75, 100)


class LeftoverLogCreate(BaseModel):
    """FR5.3. Kitchen Staff say how much of a dish was left over for a meal
    period: none, a quarter, half, three quarters or all of what was prepared.
    The quantities are then worked out from the prep quantity confirmed for that
    dish, meal period and day, so nobody types a count that means different
    things to different people.

    Bulk imports and older clients may instead send prepared_quantity and
    leftover_quantity directly."""

    menu_item_id: int
    service_period_date: date
    meal_period: Literal["Breakfast", "Lunch", "Dinner"] | None = None
    leftover_percent: int | None = None
    prepared_quantity: Decimal | None = Field(default=None, gt=0)
    leftover_quantity: Decimal | None = Field(default=None, ge=0)
    leftover_level: str | None = Field(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def _percent_or_quantities(self) -> "LeftoverLogCreate":
        if self.leftover_percent is not None:
            if self.leftover_percent not in LEFTOVER_PERCENTS:
                raise ValueError("leftover_percent must be 0, 25, 50, 75 or 100.")
            if self.meal_period is None:
                raise ValueError("meal_period is required when giving a leftover percentage.")
            return self
        if self.prepared_quantity is None or self.leftover_quantity is None:
            raise ValueError("Give leftover_percent, or both prepared_quantity and leftover_quantity.")
        # Same spirit as FR6.5's rule for waste logs: a leftover count can't
        # exceed how much was actually prepared for the service.
        if self.leftover_quantity > self.prepared_quantity:
            raise ValueError("leftover_quantity cannot exceed prepared_quantity.")
        if self.leftover_level is None:
            self.leftover_level = "Counted"
        return self


class LeftoverLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    menu_item_id: int
    service_period_date: date
    prepared_quantity: Decimal
    leftover_quantity: Decimal
    leftover_level: str
    meal_period: str | None = None
    leftover_percent: int | None = None
    staff_id: int


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_id: int
    type: str
    message: str
    status: str
    created_at: datetime
    read_at: datetime | None = None


class UnreadCountOut(BaseModel):
    unread: int
