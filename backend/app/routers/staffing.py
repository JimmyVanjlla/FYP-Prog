from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.staffing import (
    AttendanceUpdate,
    MyShiftOut,
    ShiftAssignmentCreate,
    ShiftAssignmentOut,
    ShiftClosingReportCreate,
    ShiftClosingReportOut,
    ShiftScheduleCreate,
    ShiftScheduleOut,
    StaffingRecommendationOut,
    StaffMemberOut,
)
from app.services import staffing as staffing_service

router = APIRouter(prefix="/staffing", tags=["staffing"])


@router.get("/my-schedule", response_model=list[MyShiftOut])
def list_my_schedule(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MyShiftOut]:
    """UC-SS-05 "View My Shift Schedule" — any staff member's own
    published shifts, without needing a schedule_id or going through the
    Shift Supervisor."""
    rows = staffing_service.list_my_assignments(db, user.user_id, limit=limit, offset=offset)
    return [
        MyShiftOut(
            assignment_id=a.assignment_id,
            schedule_id=s.schedule_id,
            date=s.date,
            meal_period=s.meal_period,
            station=a.station,
            attendance_status=a.attendance_status,
        )
        for a, s in rows
    ]


def _closing_report_out(db: Session, report) -> ShiftClosingReportOut:
    out = ShiftClosingReportOut.model_validate(report)
    schedule = staffing_service.get_schedule(db, report.schedule_id)
    out.forecasted_volume = staffing_service.forecasted_volume(db, schedule)
    if out.forecasted_volume is not None:
        out.variance = out.actual_order_volume - out.forecasted_volume
    return out


@router.get("/staff", response_model=list[StaffMemberOut])
def list_assignable_staff(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(Role.SHIFT_SUPERVISOR, Role.RESTAURANT_MANAGER)),
) -> list[StaffMemberOut]:
    """FR8.2 — who a Shift Supervisor can assign. GET /users is Manager-only,
    so without this the supervisor had no way to pick a staff_id."""
    return staffing_service.list_assignable_staff(db)


@router.get("/schedules", response_model=list[ShiftScheduleOut])
def list_schedules(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ShiftScheduleOut]:
    return staffing_service.list_schedules(db, limit=limit, offset=offset)


@router.post("/schedules", response_model=ShiftScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    data: ShiftScheduleCreate,
    db: Session = Depends(get_db),
    supervisor: User = Depends(require_role(Role.SHIFT_SUPERVISOR)),
) -> ShiftScheduleOut:
    """FR8.2."""
    return staffing_service.create_schedule(
        db, shift_date=data.date, meal_period=data.meal_period, published_by=supervisor.user_id
    )


@router.post("/schedules/{schedule_id}/recommendations", response_model=list[StaffingRecommendationOut])
def generate_staffing_recommendation(
    schedule_id: int,
    db: Session = Depends(get_db),
    _supervisor: User = Depends(require_role(Role.SHIFT_SUPERVISOR)),
) -> list[StaffingRecommendationOut]:
    """FR8.1."""
    try:
        schedule = staffing_service.get_schedule(db, schedule_id)
    except staffing_service.ScheduleNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    return staffing_service.calculate_staffing_recommendation(db, schedule=schedule)


@router.get("/schedules/{schedule_id}/recommendations", response_model=list[StaffingRecommendationOut])
def list_staffing_recommendations(
    schedule_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[StaffingRecommendationOut]:
    """FR8.1 — the read side; recommendations were previously only ever
    visible once, in the POST response that generated them."""
    try:
        return staffing_service.list_staffing_recommendations(db, schedule_id)
    except staffing_service.ScheduleNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")


@router.get("/schedules/{schedule_id}/assignments", response_model=list[ShiftAssignmentOut])
def list_shift_assignments(
    schedule_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[ShiftAssignmentOut]:
    """FR8.2 — "who's on this shift", viewable after the fact."""
    try:
        return staffing_service.list_shift_assignments(db, schedule_id)
    except staffing_service.ScheduleNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")


@router.post(
    "/schedules/{schedule_id}/assignments",
    response_model=ShiftAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
def assign_staff(
    schedule_id: int,
    data: ShiftAssignmentCreate,
    db: Session = Depends(get_db),
    _supervisor: User = Depends(require_role(Role.SHIFT_SUPERVISOR)),
) -> ShiftAssignmentOut:
    """FR8.2 / FR8.5."""
    try:
        return staffing_service.assign_staff(
            db, schedule_id=schedule_id, staff_id=data.staff_id, station=data.station
        )
    except staffing_service.ScheduleNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    except staffing_service.OverlappingAssignmentError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This staff member is already assigned to a station on this shift.",
        )


@router.post("/schedules/{schedule_id}/publish", response_model=ShiftScheduleOut)
def publish_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    supervisor: User = Depends(require_role(Role.SHIFT_SUPERVISOR)),
) -> ShiftScheduleOut:
    """FR8.2 / UC-SS-02 main flow step 5 (notify staff) / Alt Flow 3a (log
    staffing deviations)."""
    try:
        return staffing_service.publish_schedule(db, schedule_id, supervisor.user_id)
    except staffing_service.ScheduleNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")


@router.patch("/assignments/{assignment_id}/attendance", response_model=ShiftAssignmentOut)
def confirm_attendance(
    assignment_id: int,
    data: AttendanceUpdate,
    db: Session = Depends(get_db),
    _supervisor: User = Depends(require_role(Role.SHIFT_SUPERVISOR)),
) -> ShiftAssignmentOut:
    """FR8.3."""
    try:
        return staffing_service.confirm_attendance(
            db, assignment_id=assignment_id, attendance_status=data.attendance_status
        )
    except staffing_service.ScheduleNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")


@router.post(
    "/schedules/{schedule_id}/closing-report",
    response_model=ShiftClosingReportOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_closing_report(
    schedule_id: int,
    data: ShiftClosingReportCreate,
    db: Session = Depends(get_db),
    supervisor: User = Depends(require_role(Role.SHIFT_SUPERVISOR)),
) -> ShiftClosingReportOut:
    """FR8.4."""
    try:
        report = staffing_service.submit_closing_report(
            db,
            schedule_id=schedule_id,
            actual_order_volume=data.actual_order_volume,
            notes=data.notes,
            submitted_by=supervisor.user_id,
        )
        return _closing_report_out(db, report)
    except staffing_service.ScheduleNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    except staffing_service.ClosingReportAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A closing report already exists for this shift."
        )


@router.get("/schedules/{schedule_id}/closing-report", response_model=ShiftClosingReportOut)
def get_closing_report(
    schedule_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> ShiftClosingReportOut:
    """FR8.4 — the submitted shift summary with the forecast comparison."""
    try:
        report = staffing_service.get_closing_report(db, schedule_id)
    except staffing_service.ScheduleNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No closing report yet for this shift.")
    return _closing_report_out(db, report)
