from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ShiftScheduleCreate(BaseModel):
    date: date
    meal_period: str = Field(min_length=1, max_length=20)


class ShiftScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schedule_id: int
    date: date
    meal_period: str
    published_by: int
    status: str


class StaffingRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recommendation_id: int
    schedule_id: int
    forecast_id: int | None
    station: str
    recommended_staff_count: int


class ShiftAssignmentCreate(BaseModel):
    staff_id: int
    station: str = Field(min_length=1, max_length=50)


class ShiftAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: int
    schedule_id: int
    staff_id: int
    station: str
    attendance_status: str


class MyShiftOut(BaseModel):
    """UC-SS-05 — a staff member's own shift, with the schedule's date/
    meal_period folded in so the client doesn't need a second lookup per
    assignment."""

    assignment_id: int
    schedule_id: int
    date: date
    meal_period: str
    station: str
    attendance_status: str


class AttendanceUpdate(BaseModel):
    attendance_status: str = Field(min_length=1, max_length=20)


class ShiftClosingReportCreate(BaseModel):
    actual_order_volume: int = Field(ge=0)
    notes: str | None = None


class ShiftClosingReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    schedule_id: int
    actual_order_volume: int
    notes: str | None
    submitted_by: int
    # FR8.4 "actual vs. forecasted performance": what was forecast for the
    # shift (None when nothing was) and how far off it was. Filled in by the
    # router; they aren't stored on the report itself.
    forecasted_volume: int | None = None
    variance: int | None = None


class StaffMemberOut(BaseModel):
    """A person a Shift Supervisor can assign to a station."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    name: str
    role: str
