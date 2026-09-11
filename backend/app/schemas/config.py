from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SystemConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    config_id: int
    default_low_stock_threshold: Decimal
    leftover_rate_threshold: Decimal
    prep_deviation_threshold: Decimal
    portions_per_staff_ratio: Decimal
    monthly_budget_limit: Decimal
    near_expiry_window_days: int


class SystemConfigUpdate(BaseModel):
    """FR3.3 (default_low_stock_threshold) / FR7.5 (leftover_rate_threshold,
    explicitly 0-100%) — Restaurant Manager configures system-wide
    settings (Ch3 §3.4.2's Manager use-case list: "configure system
    settings"). All fields optional; only send what changes."""

    default_low_stock_threshold: Decimal | None = Field(default=None, ge=0)
    leftover_rate_threshold: Decimal | None = Field(default=None, ge=0, le=100)
    prep_deviation_threshold: Decimal | None = Field(default=None, ge=0, le=100)
    portions_per_staff_ratio: Decimal | None = Field(default=None, gt=0)
    monthly_budget_limit: Decimal | None = Field(default=None, gt=0)
    near_expiry_window_days: int | None = Field(default=None, ge=0)
