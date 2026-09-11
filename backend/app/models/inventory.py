"""
Module 3: Inventory Management — Ingredient, StockBatch, StockAdjustment,
RestockingRequest [M3] (Ch4 §4.3.1). Backs FR3.1-FR3.6.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    ingredient_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    current_stock: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("0"), nullable=False)
    # Nullable — falls back to SystemConfig.default_low_stock_threshold (FR3.3).
    low_stock_threshold: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)

    batches: Mapped[list["StockBatch"]] = relationship(back_populates="ingredient")


class StockBatch(Base):
    __tablename__ = "stock_batches"

    batch_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.ingredient_id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    # active | expired | depleted
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    ingredient: Mapped["Ingredient"] = relationship(back_populates="batches")


class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"

    adjustment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.ingredient_id"), nullable=False)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    adjusted_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)  # signed
    reason_category: Mapped[str] = mapped_column(String(20), nullable=False)  # spillage/spoilage/miscount
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class RestockingRequest(Base):
    __tablename__ = "restocking_requests"

    request_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.ingredient_id"), nullable=False)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    urgency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # pending | fulfilled | escalated_to_procurement
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
