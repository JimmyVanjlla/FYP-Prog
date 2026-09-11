from fastapi import APIRouter, Depends, HTTPException, status
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
)
from app.services import staffing as staffing_service

router = APIRouter(prefix="/staffing", tags=["staffing"])


@router.get("/my-schedule", response_model=list[MyShiftOut])
def list_my_schedule(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[MyShiftOut]:
    """UC-SS-05 "View My Shift Schedule" — any staff member's own
    published shifts, without needing a schedule_id or going through the
    Shift Supervisor."""
    rows = staffing_service.list_my_assignments(db, user.user_id)
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


@router.get("/schedules", response_model=list[ShiftScheduleOut])
def list_schedules(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[ShiftScheduleOut]:
    return staffing_service.list_schedules(db)


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
        return staffing_service.submit_closing_report(
            db,
            schedule_id=schedule_id,
            actual_order_volume=data.actual_order_volume,
            notes=data.notes,
            submitted_by=supervisor.user_id,
        )
    except staffing_service.ScheduleNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    except staffing_service.ClosingReportAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A closing report already exists for this shift."
        )
