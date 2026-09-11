"""
Module 10: Delivery Management — Delivery, DeliveryItem, DeliveryDiscrepancy
[M10] (Ch4 §4.3.1). Backs FR10.1-FR10.5.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Delivery(Base):
    __tablename__ = "deliveries"

    delivery_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.po_id"), unique=True, nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    # scheduled | received | delayed
    status: Mapped[str] = mapped_column(String(30), default="scheduled", nullable=False)
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)

    items: Mapped[list["DeliveryItem"]] = relationship(back_populates="delivery")


class DeliveryItem(Base):
    __tablename__ = "delivery_items"

    item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.delivery_id"), nullable=False)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.ingredient_id"), nullable=False)
    expected_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    received_quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)

    delivery: Mapped["Delivery"] = relationship(back_populates="items")


class DeliveryDiscrepancy(Base):
    __tablename__ = "delivery_discrepancies"

    discrepancy_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.delivery_id"), nullable=False)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.ingredient_id"), nullable=False)
    # shortage | damaged | wrong_item
    issue_type: Mapped[str] = mapped_column(String(20), nullable=False)
    return_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # open | resolved
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
