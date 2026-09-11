from datetime import date, datetime

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
