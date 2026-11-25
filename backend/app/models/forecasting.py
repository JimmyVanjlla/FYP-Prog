"""
Module 4: Demand Forecasting — Order, Forecast, ForecastAccuracy [M4]
(Ch4 §4.3.1). Backs FR4.1-FR4.6.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


ORDER_STATUSES = ("pending", "preparing", "completed")


class Order(Base):
    """An order for portions of one dish at a meal period. It is the raw input
    Algorithm 1 trains on (FR4.1) and, now, the sales record the kitchen works
    through: it arrives as "pending", Kitchen Staff move it to "preparing" and
    then "completed", and the portions of completed orders are what was
    actually served (leftover = confirmed prep minus served). Historical rows
    are all "completed"."""

    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.menu_item_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    meal_period: Mapped[str] = mapped_column(String(20), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", server_default="completed", nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True
    )
    # Set once the ingredients this order used have been taken off stock by the
    # end-of-day count, so the nightly job (which counts whole days) skips it.
    stock_counted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)


class Forecast(Base):
    """A Prophet prediction for one item/meal_period/date (FR4.2-FR4.3)."""

    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("menu_item_id", "meal_period", "forecast_date", name="uq_forecast_item_period_date"),
    )

    forecast_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.menu_item_id"), nullable=False)
    meal_period: Mapped[str] = mapped_column(String(20), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ForecastAccuracy(Base):
    """Predicted-vs-actual comparison, one row per forecast (FR4.4)."""

    __tablename__ = "forecast_accuracies"

    accuracy_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("forecasts.forecast_id"), unique=True, nullable=False
    )
    actual_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    accuracy_error: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
