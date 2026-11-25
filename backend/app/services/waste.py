"""
Module 6: Waste Management business logic. FR6.1-FR6.5, plus ALGORITHM
CalculateWasteCost (Ch4 §4.8.4).

Waste cost = wasted ingredient quantity × ingredient unit price, via
Module 9's SupplierPricing (Sprint 4) — see app/services/procurement.py's
get_unit_price (cheapest active supplier, 0.00 if nobody prices it yet).
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dates import end_of_day, restaurant_today
from app.models.forecasting import Forecast
from app.models.inventory import Ingredient, StockAdjustment, StockBatch
from app.models.kitchen import LeftoverLog
from app.models.menu import MenuItem, RecipeIngredientLink
from app.models.waste import WasteLog, WasteReductionTrend
from app.schemas.waste import WasteLogCreate
from app.services.procurement import get_unit_price as _get_unit_price


def service_day_stamp(service_date: date) -> datetime:
    """When a leftover's waste is recorded as having happened: the service day
    it belongs to (midday UTC), not the moment someone typed it in. A log
    entered a day late then still counts towards the right week. Today's (or a
    future) service date is stamped with the actual time."""
    if service_date >= restaurant_today():
        return datetime.now(timezone.utc)
    return datetime(service_date.year, service_date.month, service_date.day, 12, 0, tzinfo=timezone.utc)


def record_leftover_waste(db: Session, leftover_log: LeftoverLog) -> list[WasteLog]:
    """FR6.1 (leftover half) / FR6.2 — called right after a LeftoverLog is
    created (see app/services/kitchen.py::log_leftover). One LeftoverLog
    entry (denominated in servings of a dish) fans out into one WasteLog
    per ingredient in that dish's recipe, converting servings -> ingredient
    units via RecipeIngredientLink.quantity_per_serving, per Algorithm
    CalculateWasteCost step 2."""
    if leftover_log.leftover_quantity <= 0:
        return []  # nothing was left, so nothing was wasted
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
            logged_at=service_day_stamp(leftover_log.service_period_date),
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


def list_waste_logs(
    db: Session, *, ingredient_id: int | None = None, limit: int = 100, offset: int = 0
) -> list[WasteLog]:
    stmt = (
        select(WasteLog)
        .order_by(WasteLog.logged_at.desc(), WasteLog.waste_log_id.desc())
        .limit(limit)
        .offset(offset)
    )
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
        .where(WasteLog.logged_at <= end_of_day(period_end))
    ).all()
    total_cost = sum(rows, Decimal("0.00"))

    trend = WasteReductionTrend(period_start=period_start, period_end=period_end, total_waste_cost=total_cost)
    db.add(trend)
    db.commit()
    db.refresh(trend)
    return trend


def list_waste_trends(db: Session, *, limit: int = 100, offset: int = 0) -> list[WasteReductionTrend]:
    return list(
        db.scalars(
            select(WasteReductionTrend)
            .order_by(WasteReductionTrend.period_start)
            .limit(limit)
            .offset(offset)
        )
    )


class InvalidWasteEntryError(Exception):
    """FR6.5 — carries the validation message to show the user."""


def create_manual_waste_log(db: Session, data: WasteLogCreate, staff_id: int | None = None) -> WasteLog:
    """FR6.5 — a waste entry typed in by staff (rather than derived
    automatically from a leftover log or the expiry scan). Rejects anything
    that couldn't have been wasted: a negative/zero quantity (the schema
    already refuses those), or more than was originally prepared (leftover)
    or delivered (expiry batch).

    A leftover entry records the waste and its cost only: that food was never
    in stock. An expiry entry is stock being thrown away, so it also comes
    off the ingredient's stock (as a logged "spoilage" adjustment, never below
    zero) and off the batch, and a batch that is wholly wasted is marked
    depleted, which takes it, and its near-expiry alert, off the screen."""
    batch = None
    if data.source_type == "expiry":
        batch = db.get(StockBatch, data.source_ref_id)
        if batch is None:
            raise InvalidWasteEntryError("That stock batch does not exist.")
        if batch.ingredient_id != data.ingredient_id:
            raise InvalidWasteEntryError("That batch is not a batch of this ingredient.")
        if data.quantity_wasted > batch.quantity:
            raise InvalidWasteEntryError(
                f"Quantity wasted exceeds the {batch.quantity} delivered in that batch."
            )
    else:
        log = db.get(LeftoverLog, data.source_ref_id)
        if log is None:
            raise InvalidWasteEntryError("That leftover log does not exist.")
        link = db.scalars(
            select(RecipeIngredientLink)
            .where(RecipeIngredientLink.menu_item_id == log.menu_item_id)
            .where(RecipeIngredientLink.ingredient_id == data.ingredient_id)
        ).first()
        if link is None:
            raise InvalidWasteEntryError("That ingredient is not part of the dish's recipe.")
        prepared = (log.prepared_quantity * link.quantity_per_serving).quantize(Decimal("0.001"))
        if data.quantity_wasted > prepared:
            raise InvalidWasteEntryError(
                f"Quantity wasted exceeds the {prepared} originally prepared."
            )

    cost = (data.quantity_wasted * _get_unit_price(db, data.ingredient_id)).quantize(Decimal("0.01"))
    waste_log = WasteLog(
        source_type=data.source_type,
        source_ref_id=data.source_ref_id,
        ingredient_id=data.ingredient_id,
        quantity_wasted=data.quantity_wasted,
        waste_cost=cost,
    )
    db.add(waste_log)

    if batch is not None:
        ingredient = db.get(Ingredient, data.ingredient_id)
        taken = min(data.quantity_wasted, ingredient.current_stock)
        if taken > 0:
            ingredient.current_stock -= taken
            if staff_id is not None:
                db.add(
                    StockAdjustment(
                        ingredient_id=data.ingredient_id,
                        staff_id=staff_id,
                        adjusted_quantity=-taken,
                        reason_category="spoilage",
                        note=f"Expired batch #{batch.batch_id} recorded as waste",
                    )
                )
        batch.quantity -= data.quantity_wasted
        if batch.quantity <= 0:
            batch.quantity = Decimal("0.000")
            batch.status = "depleted"

    db.commit()
    db.refresh(waste_log)
    return waste_log


def _utc(moment: datetime) -> datetime:
    """A timestamp as timezone-aware UTC (SQLite hands back naive ones)."""
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def waste_summary(db: Session, *, weeks: int = 8, today: date | None = None) -> dict:
    """What the Waste screen shows: cost per calendar week (Monday to Sunday,
    oldest first, the current week last), and what was wasted most over the
    last four weeks, by ingredient and by dish. Worked out from the waste logs
    each time, so it is never stale; the stored trend rows are only what the
    weekly job saves."""
    today = today or restaurant_today()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(weeks=weeks - 1)

    logs = db.scalars(
        select(WasteLog)
        .where(WasteLog.logged_at >= datetime(first_monday.year, first_monday.month, first_monday.day, tzinfo=timezone.utc))
        .where(WasteLog.logged_at <= end_of_day(today))
    ).all()

    buckets = []
    for i in range(weeks):
        start = first_monday + timedelta(weeks=i)
        buckets.append(
            {
                "period_start": start,
                "period_end": start + timedelta(days=6),
                "leftover_cost": Decimal("0.00"),
                "expiry_cost": Decimal("0.00"),
                "total_cost": Decimal("0.00"),
                "entries": 0,
            }
        )
    for log in logs:
        index = (_utc(log.logged_at).date() - first_monday).days // 7
        if not 0 <= index < weeks:
            continue
        bucket = buckets[index]
        key = "expiry_cost" if log.source_type == "expiry" else "leftover_cost"
        bucket[key] += log.waste_cost
        bucket["total_cost"] += log.waste_cost
        bucket["entries"] += 1

    recent_from = datetime.combine(today - timedelta(days=27), datetime.min.time(), tzinfo=timezone.utc)
    recent = [l for l in logs if _utc(l.logged_at) >= recent_from]

    by_ingredient: dict[int, dict] = {}
    for log in recent:
        row = by_ingredient.setdefault(log.ingredient_id, {"cost": Decimal("0.00"), "quantity": Decimal("0")})
        row["cost"] += log.waste_cost
        row["quantity"] += log.quantity_wasted
    ingredients = {i.ingredient_id: i for i in db.scalars(select(Ingredient).where(Ingredient.ingredient_id.in_(by_ingredient)))} if by_ingredient else {}
    top_ingredients = sorted(
        (
            {
                "ingredient_id": iid,
                "name": ingredients[iid].name if iid in ingredients else f"Ingredient #{iid}",
                "unit": ingredients[iid].unit if iid in ingredients else "",
                "quantity": row["quantity"],
                "cost": row["cost"],
            }
            for iid, row in by_ingredient.items()
        ),
        key=lambda r: r["cost"],
        reverse=True,
    )[:5]

    leftover_ids = [l.source_ref_id for l in recent if l.source_type == "leftover"]
    by_dish: dict[int, Decimal] = {}
    if leftover_ids:
        dish_of = dict(
            db.execute(select(LeftoverLog.log_id, LeftoverLog.menu_item_id).where(LeftoverLog.log_id.in_(set(leftover_ids)))).all()
        )
        for log in recent:
            if log.source_type == "leftover" and log.source_ref_id in dish_of:
                dish = dish_of[log.source_ref_id]
                by_dish[dish] = by_dish.get(dish, Decimal("0.00")) + log.waste_cost
    names = {m.menu_item_id: m.name for m in db.scalars(select(MenuItem).where(MenuItem.menu_item_id.in_(by_dish)))} if by_dish else {}
    top_dishes = sorted(
        ({"menu_item_id": d, "name": names.get(d, f"Menu item #{d}"), "cost": c} for d, c in by_dish.items()),
        key=lambda r: r["cost"],
        reverse=True,
    )[:5]

    return {"weeks": buckets, "top_ingredients": top_ingredients, "top_dishes": top_dishes}


def waste_prediction(db: Session, *, days: int = 7, today: date | None = None) -> dict:
    """Expected leftover waste for the coming days.

    For each dish: the portions forecast over the period (the kitchen preps to the
    forecast) times the share the kitchen has recently been left with (the
    leftover rate over the last 14 days), costed at the dish's ingredient cost per
    portion. A dish with no recent leftover data is expected to waste nothing, and
    one that is not forecast is not listed.

        expected leftover portions = forecast portions x leftover rate
        expected cost              = expected leftover portions x ingredient cost per portion

    It is an estimate that moves as the forecast and the leftover rate do."""
    from app.services.feedback import compute_leftover_rate  # feedback imports this module's neighbours

    today = today or restaurant_today()
    end = today + timedelta(days=days - 1)
    forecast_by_item: dict[int, Decimal] = {}
    for item_id, qty in db.execute(
        select(Forecast.menu_item_id, func.sum(Forecast.predicted_quantity))
        .where(Forecast.forecast_date >= today)
        .where(Forecast.forecast_date <= end)
        .group_by(Forecast.menu_item_id)
    ):
        forecast_by_item[item_id] = Decimal(qty or 0)

    names = {i.menu_item_id: i.name for i in db.scalars(select(MenuItem).where(MenuItem.menu_item_id.in_(forecast_by_item)))}
    dishes = []
    for item_id, forecast_portions in forecast_by_item.items():
        rate = compute_leftover_rate(db, item_id, today=today)
        if rate is None or rate <= 0:
            continue
        cost_per_portion = sum(
            (
                link.quantity_per_serving * _get_unit_price(db, link.ingredient_id)
                for link in db.scalars(select(RecipeIngredientLink).where(RecipeIngredientLink.menu_item_id == item_id))
            ),
            Decimal("0"),
        )
        leftover_portions = forecast_portions * rate / 100
        dishes.append(
            {
                "menu_item_id": item_id,
                "menu_item_name": names.get(item_id, f"Dish #{item_id}"),
                "forecast_portions": forecast_portions.quantize(Decimal("0.1")),
                "leftover_rate": rate.quantize(Decimal("0.1")),
                "expected_leftover_portions": leftover_portions.quantize(Decimal("0.1")),
                "expected_cost": (leftover_portions * cost_per_portion).quantize(Decimal("0.01")),
            }
        )
    dishes.sort(key=lambda d: d["expected_cost"], reverse=True)
    return {
        "period_start": today,
        "period_end": end,
        "total_cost": sum((d["expected_cost"] for d in dishes), Decimal("0.00")),
        "total_portions": sum((d["expected_leftover_portions"] for d in dishes), Decimal("0.0")),
        "dishes": dishes,
    }
