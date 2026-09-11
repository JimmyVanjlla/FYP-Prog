"""
Module 9: Procurement & Supplier Management — Supplier, SupplierPricing,
ProcurementRecommendation, PurchaseOrder, PurchaseOrderItem, Budget,
SupplierDiscrepancy [M9] (Ch4 §4.3.1). Backs FR9.1-FR9.6.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    contact_info: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SupplierPricing(Base):
    __tablename__ = "supplier_pricing"

    pricing_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.supplier_id"), nullable=False)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.ingredient_id"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class ProcurementRecommendation(Base):
    __tablename__ = "procurement_recommendations"

    recommendation_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.ingredient_id"), nullable=False)
    # Nullable — see StaffingRecommendation.forecast_id's docstring in
    # app/models/staffing.py for the same reasoning: a procurement
    # recommendation is derived from forecasts across every menu item that
    # uses the ingredient, not one single Forecast row.
    forecast_id: Mapped[int | None] = mapped_column(ForeignKey("forecasts.forecast_id"), nullable=True)
    recommended_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    po_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.supplier_id"), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    # UC-PS-05's full lifecycle: pending_approval | approved | rejected |
    # awaiting_delivery | in_transit | delivered | discrepancy_flagged |
    # return_pending | return_resolved. The delivery-stage values (from
    # awaiting_delivery on) are mirrored from the linked Delivery's own
    # status as it progresses — see
    # app/services/delivery.py::_sync_po_status.
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    items: Mapped[list["PurchaseOrderItem"]] = relationship(back_populates="purchase_order")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.po_id"), nullable=False)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.ingredient_id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")


class Budget(Base):
    __tablename__ = "budgets"

    budget_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    month: Mapped[date] = mapped_column(Date, nullable=False)  # first day of the month
    budget_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    set_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)


class SupplierDiscrepancy(Base):
    __tablename__ = "supplier_discrepancies"

    discrepancy_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.po_id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.supplier_id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # open | resolved
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
