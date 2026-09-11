"""
Module 11: Reporting & Analytics — Report [M11] (Ch4 §4.3.1). Backs
FR11.1-FR11.6.
"""
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    __tablename__ = "reports"

    report_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # weekly_summary | forecast_accuracy | waste_cost | budget_utilisation
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # Nullable until PDF export completes.
    pdf_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # generated | failed
    status: Mapped[str] = mapped_column(String(20), default="generated", nullable=False)
