"""
Module 6: Waste Management business logic. FR6.1-FR6.5, plus ALGORITHM
CalculateWasteCost (Ch4 §4.8.4).

Waste cost = wasted ingredient quantity × ingredient unit price, via
Module 9's SupplierPricing (Sprint 4) — see app/services/procurement.py's
get_unit_price (cheapest active supplier, 0.00 if nobody prices it yet).
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kitchen import LeftoverLog
from app.models.menu import RecipeIngredientLink
from app.models.waste import WasteLog, WasteReductionTrend
from app.services.procurement import get_unit_price as _get_unit_price


def record_leftover_waste(db: Session, leftover_log: LeftoverLog) -> list[WasteLog]:
    """FR6.1 (leftover half) / FR6.2 — called right after a LeftoverLog is
    created (see app/services/kitchen.py::log_leftover). One LeftoverLog
    entry (denominated in servings of a dish) fans out into one WasteLog
    per ingredient in that dish's recipe, converting servings -> ingredient
    units via RecipeIngredientLink.quantity_per_serving, per Algorithm
    CalculateWasteCost step 2."""
    links = db.scalars(
        select(RecipeIngredientLink).where(RecipeIngredientLink.menu_item_id == leftover_log.menu_item_id)
    ).all()

    created: list[WasteLog] = []
    for link in links:
        ingredient_qty_wasted = (leftover_log.leftover_quantity * link.quantity_per_serving).quantize(
            Decimal("0.001")
        )
        cost = (ingredient_qty_wasted * _get_unit_price(db, link.ingredient_id)).quantize(Decimal("0.01"))
        waste_log = WasteLog(
            source_type="leftover",
            source_ref_id=leftover_log.log_id,
            ingredient_id=link.ingredient_id,
            quantity_wasted=ingredient_qty_wasted,
            waste_cost=cost,
        )
        db.add(waste_log)
        created.append(waste_log)

    db.commit()
    for w in created:
        db.refresh(w)
    return created


def record_expiry_waste(db: Session, expiry_waste_events: list[dict]) -> list[WasteLog]:
    """FR6.1 (expiry half) / FR6.2 — called with the expiry_waste_events
    output of app/services/inventory.py::check_near_expiry_batches
    (Algorithm CheckNearExpiryBatches). Already ingredient-denominated
    (Algorithm CalculateWasteCost step 3), so no conversion needed."""
    created: list[WasteLog] = []
    for event in expiry_waste_events:
        cost = (Decimal(str(event["quantity"])) * _get_unit_price(db, event["ingredient_id"])).quantize(
            Decimal("0.01")
        )
        waste_log = WasteLog(
            source_type="expiry",
            source_ref_id=event["source_ref_id"],
            ingredient_id=event["ingredient_id"],
            quantity_wasted=Decimal(str(event["quantity"])),
            waste_cost=cost,
        )
        db.add(waste_log)
        created.append(waste_log)

    db.commit()
    for w in created:
        db.refresh(w)
    return created


def list_waste_logs(db: Session, *, ingredient_id: int | None = None) -> list[WasteLog]:
    stmt = select(WasteLog).order_by(WasteLog.logged_at.desc())
    if ingredient_id is not None:
        stmt = stmt.where(WasteLog.ingredient_id == ingredient_id)
    return list(db.scalars(stmt))


def aggregate_waste_reduction_trend(
    db: Session, *, period_start: date, period_end: date
) -> WasteReductionTrend:
    """FR6.3 — rolls up WasteLog cost over [period_start, period_end] into
    one WasteReductionTrend row, so waste-cost-over-time can be charted
    without re-summing raw logs on every dashboard load."""
    rows = db.scalars(
        select(WasteLog.waste_cost)
        .where(WasteLog.logged_at >= period_start)
        .where(WasteLog.logged_at <= period_end)
    ).all()
    total_cost = sum(rows, Decimal("0.00"))

    trend = WasteReductionTrend(period_start=period_start, period_end=period_end, total_waste_cost=total_cost)
    db.add(trend)
    db.commit()
    db.refresh(trend)
    return trend


def list_waste_trends(db: Session) -> list[WasteReductionTrend]:
    return list(db.scalars(select(WasteReductionTrend).order_by(WasteReductionTrend.period_start)))
