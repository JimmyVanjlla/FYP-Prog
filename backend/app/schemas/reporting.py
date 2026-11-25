from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class WeeklyReportRequest(BaseModel):
    period_start: date
    period_end: date


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    type: str
    period_start: date
    period_end: date
    generated_at: datetime
    pdf_path: str | None
    status: str


class ForecastAccuracyRowOut(BaseModel):
    menu_item_id: int
    meal_period: str
    forecast_date: date
    predicted: Decimal
    actual: Decimal
    error: Decimal


class ForecastAccuracySectionOut(BaseModel):
    scored_forecasts: int
    mean_error: float | None
    rows: list[ForecastAccuracyRowOut]


class WasteSectionOut(BaseModel):
    leftover_cost: Decimal
    expiry_cost: Decimal
    total_cost: Decimal
    log_count: int


class BudgetSectionOut(BaseModel):
    limit: Decimal
    spent: Decimal
    utilisation_pct: Decimal


class LeftoverDishRowOut(BaseModel):
    menu_item_name: str
    prepared: float
    served: float
    leftover: float
    leftover_percent: float


class LeftoverSectionOut(BaseModel):
    """The % leftover calculation: leftover = confirmed prep - portions served."""

    prepared: float = 0
    served: float = 0
    leftover: float = 0
    leftover_percent: float = 0
    dishes: list[LeftoverDishRowOut] = []


class ShiftStaffOut(BaseModel):
    name: str
    station: str
    attendance: str


class ShiftAssignmentOut(BaseModel):
    date: date
    meal_period: str
    staff: list[ShiftStaffOut]


class ReportSummaryOut(BaseModel):
    """UC-RA-01 — a report's contents as data."""

    report_id: int
    type: str
    status: str
    period_start: date
    period_end: date
    generated_at: datetime | None = None
    forecast_accuracy: ForecastAccuracySectionOut
    waste: WasteSectionOut
    budget: BudgetSectionOut
    leftover: LeftoverSectionOut = LeftoverSectionOut()
    staffing: list[ShiftAssignmentOut] = []
