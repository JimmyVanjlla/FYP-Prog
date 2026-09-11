"""
Module 8: Staff Scheduling — ShiftSchedule, StaffingRecommendation,
ShiftAssignment, ShiftClosingReport [M8] (Ch4 §4.3.1). Backs FR8.1-FR8.5.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShiftSchedule(Base):
    __tablename__ = "shift_schedules"

    schedule_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_period: Mapped[str] = mapped_column(String(20), nullable=False)
    published_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    # draft | published
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)

    assignments: Mapped[list["ShiftAssignment"]] = relationship(back_populates="schedule")


class StaffingRecommendation(Base):
    __tablename__ = "staffing_recommendations"

    recommendation_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("shift_schedules.schedule_id"), nullable=False)
    # Nullable, diverging slightly from Ch4's dictionary (which shows a
    # single required forecast_id): Algorithm 3 (Ch4 §4.8.3) sums
    # total_forecasted_portions across *every* menu item's forecast for
    # the shift's date/meal-period, so one StaffingRecommendation is
    # really derived from many Forecast rows, not one — and the
    # fallback-to-past-shift path (Alt Flow 3a) has no forecast at all.
    # Kept as a best-effort pointer to one representative forecast rather
    # than a misleading single required reference.
    forecast_id: Mapped[int | None] = mapped_column(ForeignKey("forecasts.forecast_id"), nullable=True)
    station: Mapped[str] = mapped_column(String(50), nullable=False)
    recommended_staff_count: Mapped[int] = mapped_column(Integer, nullable=False)


class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    assignment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("shift_schedules.schedule_id"), nullable=False)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    station: Mapped[str] = mapped_column(String(50), nullable=False)
    # unconfirmed | confirmed | no_show
    attendance_status: Mapped[str] = mapped_column(String(20), default="unconfirmed", nullable=False)

    schedule: Mapped["ShiftSchedule"] = relationship(back_populates="assignments")


class ShiftClosingReport(Base):
    __tablename__ = "shift_closing_reports"

    report_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("shift_schedules.schedule_id"), unique=True, nullable=False
    )
    actual_order_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
