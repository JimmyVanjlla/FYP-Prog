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
