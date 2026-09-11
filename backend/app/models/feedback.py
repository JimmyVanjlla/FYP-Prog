"""
Module 7: Portion & Forecast Feedback — PortionRecommendation [M7] (Ch4
§4.3.1). Backs FR7.1-FR7.5.
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PortionRecommendation(Base):
    __tablename__ = "portion_recommendations"

    recommendation_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.menu_item_id"), nullable=False)
    leftover_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    suggested_portion_size: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
