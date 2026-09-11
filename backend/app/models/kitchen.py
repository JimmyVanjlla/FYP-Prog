"""
Module 5: Kitchen Operations — PrepRecommendation, PrepConfirmation,
LeftoverLog, Notification [M5] (Ch4 §4.3.1). Backs FR5.1-FR5.5.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PrepRecommendation(Base):
    __tablename__ = "prep_recommendations"

    recommendation_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.menu_item_id"), nullable=False)
    forecast_id: Mapped[int] = mapped_column(ForeignKey("forecasts.forecast_id"), nullable=False)
    meal_period: Mapped[str] = mapped_column(String(20), nullable=False)
    recommended_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class PrepConfirmation(Base):
    __tablename__ = "prep_confirmations"

    confirmation_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("prep_recommendations.recommendation_id"), unique=True, nullable=False
    )
    confirmed_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Required when the deviation from the recommendation exceeds the
    # configured threshold (FR5.5); nullable otherwise.
    deviation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)


class LeftoverLog(Base):
    __tablename__ = "leftover_logs"

    log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.menu_item_id"), nullable=False)
    service_period_date: Mapped[date] = mapped_column(Date, nullable=False)
    prepared_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    leftover_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # e.g. "Partially Eaten", "Mostly Uneaten"
    leftover_level: Mapped[str] = mapped_column(String(20), nullable=False)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. prep_update, high_demand_alert
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # sent | queued_for_retry | failed
    status: Mapped[str] = mapped_column(String(20), default="queued_for_retry", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
