"""
Shared Configuration — SystemConfig [Shared] (Ch4 §4.3.1). Single-row table
of restaurant-wide thresholds/ratios referenced across modules: low-stock
default, leftover-rate threshold, prep-deviation threshold, portions-per-
staff ratio, monthly budget default, near-expiry window.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemConfig(Base):
    __tablename__ = "system_config"

    config_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    default_low_stock_threshold: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), default=Decimal("10.000"), nullable=False
    )
    leftover_rate_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("15.00"), nullable=False
    )
    prep_deviation_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("10.00"), nullable=False
    )
    portions_per_staff_ratio: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("30.00"), nullable=False
    )
    monthly_budget_limit: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("8000.00"), nullable=False
    )
    near_expiry_window_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Day through which forecasted/actual consumption has already been
    # deducted from ingredient stock (FR3.1) — makes the daily job
    # idempotent. Null until its first run, which starts counting from
    # yesterday rather than back-deducting history nobody asked to apply.
    stock_consumption_applied_through: Mapped[date | None] = mapped_column(Date, nullable=True)
