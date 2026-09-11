"""
Module 8: Staff Scheduling business logic. FR8.1-FR8.5, plus ALGORITHM
CalculateStaffingRecommendation (Ch4 §4.8.3 / UC-SS-01).
"""
import math
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.forecasting import Forecast
from app.models.staffing import ShiftAssignment, ShiftClosingReport, ShiftSchedule, StaffingRecommendation
from app.services import notifications as notification_service
from app.services.config import get_or_create_config

# Ch4 UI mockups reference these two stations by name (§4.4.1); Module 8's
# data dictionary has no separate "Station" entity, so this is a fixed list
# rather than something configured per-restaurant, consistent with the
# scope of an individually developed FYP (Ch2 §2.2.1).
DEFAULT_STATIONS = ["Kitchen", "Front of House"]


class ScheduleNotFoundError(Exception):
    pass


class OverlappingAssignmentError(Exception):
    """FR8.5."""


class ClosingReportAlreadyExistsError(Exception):
    pass


def calculate_staffing_recommendation(
    db: Session, *, schedule: ShiftSchedule, stations: list[str] | None = None
) -> list[StaffingRecommendation]:
    """ALGORITHM CalculateStaffingRecommendation."""
    stations = stations or DEFAULT_STATIONS
    ratio = get_or_create_config(db).portions_per_staff_ratio

    forecasts = db.scalars(
        select(Forecast)
        .where(Forecast.forecast_date == schedule.date)
        .where(Forecast.meal_period == schedule.meal_period)
    ).all()

    representative_forecast_id: int | None = None
    if forecasts:
        total_forecasted_portions = sum((f.predicted_quantity for f in forecasts), Decimal("0"))
        representative_forecast_id = forecasts[0].forecast_id
    else:
        # Step 1-3 — UC-SS-01 Alt Flow 3a: no forecast yet, fall back to
        # the most recent comparable (same meal_period) shift's actual
        # order volume from its closing report.
        fallback = db.scalars(
            select(ShiftClosingReport)
            .join(ShiftSchedule, ShiftClosingReport.schedule_id == ShiftSchedule.schedule_id)
            .where(ShiftSchedule.meal_period == schedule.meal_period)
            .where(ShiftSchedule.date < schedule.date)
            .order_by(ShiftSchedule.date.desc())
        ).first()
        total_forecasted_portions = Decimal(fallback.actual_order_volume) if fallback else Decimal("0")

    station_count = len(stations)
    recommendations: list[StaffingRecommendation] = []
    for station in stations:
        station_share = total_forecasted_portions / station_count if station_count else Decimal("0")
        recommended_staff = math.ceil(station_share / ratio) if ratio else 0
        recommendation = StaffingRecommendation(
            schedule_id=schedule.schedule_id,
            forecast_id=representative_forecast_id,
            station=station,
            recommended_staff_count=max(recommended_staff, 0),
        )
        db.add(recommendation)
        recommendations.append(recommendation)

    db.commit()
    for r in recommendations:
        db.refresh(r)
    return recommendations


def create_schedule(db: Session, *, shift_date: date, meal_period: str, published_by: int) -> ShiftSchedule:
    schedule = ShiftSchedule(date=shift_date, meal_period=meal_period, published_by=published_by, status="draft")
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def list_schedules(db: Session) -> list[ShiftSchedule]:
    return list(db.scalars(select(ShiftSchedule).order_by(ShiftSchedule.date.desc())))


def get_schedule(db: Session, schedule_id: int) -> ShiftSchedule:
    schedule = db.get(ShiftSchedule, schedule_id)
    if schedule is None:
        raise ScheduleNotFoundError
    return schedule


def list_my_assignments(db: Session, staff_id: int) -> list[tuple[ShiftAssignment, ShiftSchedule]]:
    """UC-SS-05 "View My Shift Schedule" — an entire use case that was
    missing: any staff member should be able to see their own published
    shifts (date, meal period, role/station) without knowing a
    schedule_id in advance or going through the Shift Supervisor. Only
    published schedules are included — a draft schedule isn't "my
    schedule" yet."""
    rows = db.execute(
        select(ShiftAssignment, ShiftSchedule)
        .join(ShiftSchedule, ShiftAssignment.schedule_id == ShiftSchedule.schedule_id)
        .where(ShiftAssignment.staff_id == staff_id)
        .where(ShiftSchedule.status == "published")
        .order_by(ShiftSchedule.date)
    ).all()
    return [(a, s) for a, s in rows]


def list_staffing_recommendations(db: Session, schedule_id: int) -> list[StaffingRecommendation]:
    """FR8.1 — recommendations were previously only ever returned once, at
    the moment POST .../recommendations was called; reloading the
    schedule later had no way to see them again."""
    get_schedule(db, schedule_id)  # 404s if missing
    return list(
        db.scalars(select(StaffingRecommendation).where(StaffingRecommendation.schedule_id == schedule_id))
    )


def list_shift_assignments(db: Session, schedule_id: int) -> list[ShiftAssignment]:
    """FR8.2 — same gap as above: a Shift Supervisor could publish a
    schedule and assign staff, but there was no way to see "who's on this
    shift" after the fact without re-reading each POST response."""
    get_schedule(db, schedule_id)
    return list(db.scalars(select(ShiftAssignment).where(ShiftAssignment.schedule_id == schedule_id)))


def assign_staff(db: Session, *, schedule_id: int, staff_id: int, station: str) -> ShiftAssignment:
    """FR8.2 / FR8.5 — rejects assigning the same staff member to two
    stations on the same shift (an overlapping time slot, since one
    ShiftSchedule row is one date+meal_period)."""
    schedule = get_schedule(db, schedule_id)
    existing = db.scalars(
        select(ShiftAssignment)
        .where(ShiftAssignment.schedule_id == schedule_id)
        .where(ShiftAssignment.staff_id == staff_id)
    ).first()
    if existing is not None:
        raise OverlappingAssignmentError

    assignment = ShiftAssignment(schedule_id=schedule.schedule_id, staff_id=staff_id, station=station)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def publish_schedule(db: Session, schedule_id: int, published_by: int) -> ShiftSchedule:
    """FR8.2. Also covers two things UC-SS-02's main/alt flows name that
    weren't previously wired to publishing at all:
      - step 5: notify each assigned staff member of their shift.
      - Alt Flow 3a: log it when the actual headcount at a station
        deviates from what Algorithm 3 (Ch4 SS4.8.3) recommended, "for
        later comparison against actual shift performance" — via
        AuditLog, the same mechanism Module 1 already uses for this kind
        of record, since Ch4's dictionary has no dedicated table for it."""
    schedule = get_schedule(db, schedule_id)
    schedule.status = "published"

    assignments = list(
        db.scalars(select(ShiftAssignment).where(ShiftAssignment.schedule_id == schedule_id))
    )
    for assignment in assignments:
        notification_service.notify(
            db,
            recipient_id=assignment.staff_id,
            type_="shift_published",
            message=f"You're scheduled for {schedule.date} ({schedule.meal_period}), station: {assignment.station}.",
        )

    recommendations = list(
        db.scalars(select(StaffingRecommendation).where(StaffingRecommendation.schedule_id == schedule_id))
    )
    actual_by_station: dict[str, int] = {}
    for assignment in assignments:
        actual_by_station[assignment.station] = actual_by_station.get(assignment.station, 0) + 1
    for reco in recommendations:
        actual = actual_by_station.get(reco.station, 0)
        if actual != reco.recommended_staff_count:
            db.add(
                AuditLog(
                    user_id=published_by,
                    action=(
                        f"staffing_deviation:schedule={schedule_id}:station={reco.station}:"
                        f"recommended={reco.recommended_staff_count}:actual={actual}"
                    ),
                )
            )

    db.commit()
    db.refresh(schedule)
    return schedule


def confirm_attendance(db: Session, *, assignment_id: int, attendance_status: str) -> ShiftAssignment:
    """FR8.3 — shift opening: confirm staff attendance and station."""
    assignment = db.get(ShiftAssignment, assignment_id)
    if assignment is None:
        raise ScheduleNotFoundError
    assignment.attendance_status = attendance_status
    db.commit()
    db.refresh(assignment)
    return assignment


def submit_closing_report(
    db: Session, *, schedule_id: int, actual_order_volume: int, notes: str | None, submitted_by: int
) -> ShiftClosingReport:
    """FR8.4."""
    get_schedule(db, schedule_id)  # 404s if missing
    existing = db.scalars(
        select(ShiftClosingReport).where(ShiftClosingReport.schedule_id == schedule_id)
    ).first()
    if existing is not None:
        raise ClosingReportAlreadyExistsError

    report = ShiftClosingReport(
        schedule_id=schedule_id,
        actual_order_volume=actual_order_volume,
        notes=notes,
        submitted_by=submitted_by,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report
