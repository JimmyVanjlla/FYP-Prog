"""
Module 6: Waste Management — WasteLog, WasteReductionTrend [M6] (Ch4
§4.3.1). Backs FR6.1-FR6.5.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WasteLog(Base):
    __tablename__ = "waste_logs"

    waste_log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 'leftover' (sourced from LeftoverLog) or 'expiry' (sourced from
    # StockBatch) — a polymorphic discriminator rather than a fixed FK,
    # since source_ref_id can point at either table (Ch4 §4.3.1).
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.ingredient_id"), nullable=False)
    quantity_wasted: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    waste_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class WasteReductionTrend(Base):
    __tablename__ = "waste_reduction_trends"

    trend_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    total_waste_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
