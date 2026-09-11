import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.reporting import ReportOut, WeeklyReportRequest
from app.services import reporting as reporting_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=list[ReportOut])
def list_reports(
    db: Session = Depends(get_db), _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER))
) -> list[ReportOut]:
    """FR11.1."""
    return reporting_service.list_reports(db)


@router.post("/weekly", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def generate_weekly_report(
    data: WeeklyReportRequest,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> ReportOut:
    """FR11.1-FR11.6 — manual on-demand trigger; runs automatically via
    Celery Beat every Monday otherwise (see app/tasks/reporting_tasks.py)."""
    try:
        return reporting_service.generate_weekly_report(
            db, period_start=data.period_start, period_end=data.period_end
        )
    except reporting_service.NoDataForPeriodError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No data is available for this date range.",
        )


@router.get("/{report_id}/download")
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> FileResponse:
    """FR11.2."""
    report = reporting_service.get_report(db, report_id)
    if report is None or not report.pdf_path or not os.path.exists(report.pdf_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report PDF not found.")
    return FileResponse(report.pdf_path, media_type="application/pdf", filename=os.path.basename(report.pdf_path))
