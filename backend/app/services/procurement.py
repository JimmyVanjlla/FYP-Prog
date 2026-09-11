"""
Module 9: Procurement & Supplier Management business logic. FR9.1-FR9.6.

No Ch4 §4.8 pseudocode algorithm covers purchase-order recommendation
generation (only 4 algorithms are specified there, none for FR9.2) — the
heuristic below (forecasted consumption minus current stock) is this
module's own reasonable interpretation of "based on forecasted demand and
current stock levels", not a transcription of report pseudocode.
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecasting import Forecast
from app.models.inventory import Ingredient
from app.models.menu import RecipeIngredientLink
from app.models.procurement import (
    Budget,
    ProcurementRecommendation,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierDiscrepancy,
    SupplierPricing,
)
from app.services.config import get_or_create_config


class NotFoundError(Exception):
    pass


class InvalidPurchaseOrderError(Exception):
    """FR9.6 — zero/negative quantity line items."""


def get_unit_price(db: Session, ingredient_id: int) -> Decimal:
    """The real pricing lookup Sprint 1 (menu profit margin) and Sprint 3
    (waste cost) both stubbed pending this module. Picks the cheapest
    active supplier's price; falls back to 0.00 if no supplier prices this
    ingredient yet, so callers never have to special-case "no price"."""
    price = db.scalar(
        select(SupplierPricing.unit_price)
        .join(Supplier, SupplierPricing.supplier_id == Supplier.supplier_id)
        .where(SupplierPricing.ingredient_id == ingredient_id)
        .where(Supplier.is_active.is_(True))
        .order_by(SupplierPricing.unit_price.asc())
    )
    return price if price is not None else Decimal("0.00")


# --- Suppliers & pricing -----------------------------------------------


def create_supplier(db: Session, *, name: str, contact_info: str) -> Supplier:
    supplier = Supplier(name=name, contact_info=contact_info, is_active=True)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def list_suppliers(db: Session) -> list[Supplier]:
    return list(db.scalars(select(Supplier).order_by(Supplier.name)))


def set_supplier_pricing(db: Session, *, supplier_id: int, ingredient_id: int, unit_price: Decimal) -> SupplierPricing:
    existing = db.scalars(
        select(SupplierPricing)
        .where(SupplierPricing.supplier_id == supplier_id)
        .where(SupplierPricing.ingredient_id == ingredient_id)
    ).first()
    if existing is not None:
        existing.unit_price = unit_price
        db.commit()
        db.refresh(existing)
        return existing

    pricing = SupplierPricing(supplier_id=supplier_id, ingredient_id=ingredient_id, unit_price=unit_price)
    db.add(pricing)
    db.commit()
    db.refresh(pricing)
    return pricing


def list_supplier_pricing(
    db: Session, *, supplier_id: int | None = None, ingredient_id: int | None = None
) -> list[SupplierPricing]:
    """FR9.1 — "supplier directory with pricing" implies being able to see
    it, not just set it; there was no way to view what's been priced
    without a listing endpoint."""
    stmt = select(SupplierPricing)
    if supplier_id is not None:
        stmt = stmt.where(SupplierPricing.supplier_id == supplier_id)
    if ingredient_id is not None:
        stmt = stmt.where(SupplierPricing.ingredient_id == ingredient_id)
    return list(db.scalars(stmt))


# --- Procurement recommendations (FR9.2) --------------------------------


def generate_procurement_recommendations(db: Session, *, horizon_days: int = 7) -> list[ProcurementRecommendation]:
    """For each ingredient, sums forecasted portions (over the next
    horizon_days) of every menu item that uses it, converts to ingredient
    units via each recipe link, and recommends the shortfall against
    current stock (only when positive)."""
    today = date.today()
    horizon_end = today + timedelta(days=horizon_days)

    links = db.scalars(select(RecipeIngredientLink)).all()
    forecasts = db.scalars(
        select(Forecast).where(Forecast.forecast_date >= today).where(Forecast.forecast_date <= horizon_end)
    ).all()
    forecast_by_item: dict[int, list[Forecast]] = {}
    for f in forecasts:
        forecast_by_item.setdefault(f.menu_item_id, []).append(f)

    consumption_by_ingredient: dict[int, Decimal] = {}
    representative_forecast: dict[int, int] = {}
    for link in links:
        item_forecasts = forecast_by_item.get(link.menu_item_id, [])
        total_portions = sum((f.predicted_quantity for f in item_forecasts), Decimal("0"))
        if total_portions == 0:
            continue
        consumption_by_ingredient[link.ingredient_id] = (
            consumption_by_ingredient.get(link.ingredient_id, Decimal("0"))
            + total_portions * link.quantity_per_serving
        )
        representative_forecast.setdefault(link.ingredient_id, item_forecasts[0].forecast_id)

    recommendations: list[ProcurementRecommendation] = []
    for ingredient_id, forecasted_consumption in consumption_by_ingredient.items():
        ingredient = db.get(Ingredient, ingredient_id)
        if ingredient is None:
            continue
        shortfall = forecasted_consumption - ingredient.current_stock
        if shortfall <= 0:
            continue
        recommendation = ProcurementRecommendation(
            ingredient_id=ingredient_id,
            forecast_id=representative_forecast.get(ingredient_id),
            recommended_quantity=shortfall.quantize(Decimal("0.001")),
        )
        db.add(recommendation)
        recommendations.append(recommendation)

    db.commit()
    for r in recommendations:
        db.refresh(r)
    return recommendations


def list_procurement_recommendations(db: Session) -> list[ProcurementRecommendation]:
    return list(db.scalars(select(ProcurementRecommendation).order_by(ProcurementRecommendation.recommendation_id.desc())))


# --- Purchase orders (FR9.3 / FR9.6) ------------------------------------


def create_purchase_order(
    db: Session, *, supplier_id: int, created_by: int, line_items: list[dict]
) -> tuple[PurchaseOrder, bool]:
    """Returns (purchase_order, exceeds_budget) — FR9.6: over-budget
    doesn't block submission, it's surfaced as a warning to the caller."""
    if not line_items:
        raise InvalidPurchaseOrderError
    for item in line_items:
        if item["quantity"] <= 0:
            raise InvalidPurchaseOrderError

    total_cost = Decimal("0.00")
    po = PurchaseOrder(supplier_id=supplier_id, created_by=created_by, total_cost=Decimal("0.00"))
    db.add(po)
    db.flush()

    for item in line_items:
        unit_price = get_unit_price(db, item["ingredient_id"])
        line_cost = (unit_price * item["quantity"]).quantize(Decimal("0.01"))
        total_cost += line_cost
        db.add(
            PurchaseOrderItem(
                po_id=po.po_id,
                ingredient_id=item["ingredient_id"],
                quantity=item["quantity"],
                unit_price=unit_price,
            )
        )

    po.total_cost = total_cost
    db.commit()
    db.refresh(po)

    exceeds_budget = _exceeds_monthly_budget(db, total_cost)
    return po, exceeds_budget


def _exceeds_monthly_budget(db: Session, additional_cost: Decimal) -> bool:
    today = date.today()
    month_start = today.replace(day=1)
    budget = db.scalars(select(Budget).where(Budget.month == month_start)).first()
    limit = budget.budget_limit if budget else get_or_create_config(db).monthly_budget_limit

    spent_rows = db.scalars(
        select(PurchaseOrder.total_cost)
        .where(PurchaseOrder.created_at >= month_start)
        .where(PurchaseOrder.status != "rejected")
    ).all()
    total_spent = sum(spent_rows, Decimal("0.00"))
    return (total_spent + additional_cost) > limit


def approve_purchase_order(db: Session, po_id: int, approved_by: int) -> PurchaseOrder:
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise NotFoundError
    po.status = "approved"
    po.approved_by = approved_by
    db.commit()
    db.refresh(po)
    return po


def reject_purchase_order(db: Session, po_id: int) -> PurchaseOrder:
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise NotFoundError
    po.status = "rejected"
    db.commit()
    db.refresh(po)
    return po


def list_purchase_orders(db: Session, *, status: str | None = None) -> list[PurchaseOrder]:
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    if status is not None:
        stmt = stmt.where(PurchaseOrder.status == status)
    return list(db.scalars(stmt))


# --- Budget (FR9.4) ------------------------------------------------------


def set_monthly_budget(db: Session, *, month: date, budget_limit: Decimal, set_by: int) -> Budget:
    month_start = month.replace(day=1)
    existing = db.scalars(select(Budget).where(Budget.month == month_start)).first()
    if existing is not None:
        existing.budget_limit = budget_limit
        db.commit()
        db.refresh(existing)
        return existing

    budget = Budget(month=month_start, budget_limit=budget_limit, set_by=set_by)
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def list_budgets(db: Session) -> list[Budget]:
    """FR9.4 — "track monthly procurement budget configuration" implies
    being able to see the configured history, not just set it once."""
    return list(db.scalars(select(Budget).order_by(Budget.month.desc())))


# --- Supplier discrepancies (FR9.5) --------------------------------------


def flag_supplier_discrepancy(db: Session, *, po_id: int, supplier_id: int, description: str) -> SupplierDiscrepancy:
    discrepancy = SupplierDiscrepancy(po_id=po_id, supplier_id=supplier_id, description=description, status="open")
    db.add(discrepancy)
    db.commit()
    db.refresh(discrepancy)
    return discrepancy


def list_supplier_discrepancies(db: Session) -> list[SupplierDiscrepancy]:
    return list(db.scalars(select(SupplierDiscrepancy).order_by(SupplierDiscrepancy.discrepancy_id.desc())))
