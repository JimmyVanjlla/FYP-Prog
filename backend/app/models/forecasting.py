"""
Module 4: Demand Forecasting — Order, Forecast, ForecastAccuracy [M4]
(Ch4 §4.3.1). Backs FR4.1-FR4.6.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Order(Base):
    """Historical order record — the raw input Algorithm 1 trains on (FR4.1)."""

    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.menu_item_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    meal_period: Mapped[str] = mapped_column(String(20), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)


class Forecast(Base):
    """A Prophet prediction for one item/meal_period/date (FR4.2-FR4.3)."""

    __tablename__ = "forecasts"

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
