"""Module 3: Inventory Management business logic. FR3.1-FR3.6, plus
Algorithm "CheckLowStockThreshold" and "CheckNearExpiryBatches" (Ch4
§4.8.4)."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.forecasting import Forecast, Order
from app.models.inventory import Ingredient, RestockingRequest, StockAdjustment, StockBatch
from app.models.menu import RecipeIngredientLink
from app.schemas.inventory import IngredientCreate, RestockingRequestCreate, StockAdjustmentCreate, StockBatchCreate
from app.services import notifications as notification_service
from app.services.config import get_or_create_config


class IngredientNotFoundError(Exception):
    pass


class StockWouldGoNegativeError(Exception):
    """FR3.6."""


def create_ingredient(db: Session, data: IngredientCreate) -> Ingredient:
    ingredient = Ingredient(
        name=data.name,
        unit=data.unit,
        current_stock=data.current_stock,
        low_stock_threshold=data.low_stock_threshold,
    )
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    return ingredient


def list_ingredients(db: Session, *, limit: int | None = None, offset: int = 0) -> list[Ingredient]:
    """limit=None (the default) returns everything — used internally by
    list_low_stock_ingredients, which has to scan the full table to filter
    correctly before paginating its own, separately-sized result. The
    GET /inventory/ingredients router always passes an explicit limit."""
    stmt = select(Ingredient).order_by(Ingredient.name).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def get_ingredient(db: Session, ingredient_id: int) -> Ingredient:
    ingredient = db.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise IngredientNotFoundError
    return ingredient


def set_low_stock_threshold(db: Session, ingredient_id: int, threshold: Decimal | None) -> Ingredient:
    """FR3.3 — Inventory Staff sets an ingredient-specific override; passing
    None clears it, falling back to SystemConfig.default_low_stock_threshold."""
    ingredient = get_ingredient(db, ingredient_id)
    ingredient.low_stock_threshold = threshold
    db.commit()
    db.refresh(ingredient)
    return ingredient


def record_stock_adjustment(
    db: Session, staff_id: int, data: StockAdjustmentCreate
) -> StockAdjustment:
    """FR3.4 / FR3.6 — manual correction for spillage/spoilage/miscount.
    Rejected if it would drive stock negative."""
    ingredient = get_ingredient(db, data.ingredient_id)
    new_stock = ingredient.current_stock + data.adjusted_quantity
    if new_stock < 0:
        raise StockWouldGoNegativeError

    ingredient.current_stock = new_stock
    adjustment = StockAdjustment(
        ingredient_id=data.ingredient_id,
        staff_id=staff_id,
        adjusted_quantity=data.adjusted_quantity,
        reason_category=data.reason_category,
        note=data.note,
    )
    db.add(adjustment)
    db.commit()
    db.refresh(adjustment)
    return adjustment


def record_stock_batch(db: Session, data: StockBatchCreate) -> StockBatch:
    """FR3.1 / FR3.2 — logs a received batch (e.g. from a delivery — Module
    10's Delivery confirmation will call into this in Sprint 4) and adds
    its quantity onto the ingredient's running stock level."""
    ingredient = get_ingredient(db, data.ingredient_id)
    ingredient.current_stock += data.quantity
    batch = StockBatch(
        ingredient_id=data.ingredient_id,
        quantity=data.quantity,
        received_date=data.received_date,
        expiry_date=data.expiry_date,
        status="active",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def list_stock_batches(
    db: Session, *, ingredient_id: int | None = None, limit: int = 100, offset: int = 0
) -> list[StockBatch]:
    """FR3.2 — batch/expiry tracking needs to be viewable, not just
    logged; previously the near-expiry Celery task was the only thing
    that ever looked at StockBatch rows again after creation."""
    stmt = (
        select(StockBatch)
        .order_by(StockBatch.expiry_date, StockBatch.batch_id)
        .limit(limit)
        .offset(offset)
    )
    if ingredient_id is not None:
        stmt = stmt.where(StockBatch.ingredient_id == ingredient_id)
    return list(db.scalars(stmt))


def list_stock_adjustments(
    db: Session, *, ingredient_id: int | None = None, limit: int = 100, offset: int = 0
) -> list[StockAdjustment]:
    """FR3.4 — adjustment history, viewable rather than write-only."""
    stmt = (
        select(StockAdjustment)
        .order_by(StockAdjustment.timestamp.desc(), StockAdjustment.adjustment_id.desc())
        .limit(limit)
        .offset(offset)
    )
    if ingredient_id is not None:
        stmt = stmt.where(StockAdjustment.ingredient_id == ingredient_id)
    return list(db.scalars(stmt))


def create_restocking_request(
    db: Session, requested_by: int, data: RestockingRequestCreate
) -> RestockingRequest:
    """FR3.5 — Kitchen Staff requests more of an ingredient from Inventory Staff."""
    get_ingredient(db, data.ingredient_id)  # 404s if it doesn't exist
    request = RestockingRequest(
        ingredient_id=data.ingredient_id,
        requested_by=requested_by,
        quantity=data.quantity,
        urgency=data.urgency,
        status="pending",
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def list_restocking_requests(
    db: Session, *, status: str | None = None, limit: int = 100, offset: int = 0
) -> list[RestockingRequest]:
    stmt = (
        select(RestockingRequest)
        .order_by(RestockingRequest.urgency.desc(), RestockingRequest.request_id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(RestockingRequest.status == status)
    return list(db.scalars(stmt))


def update_restocking_request_status(db: Session, request_id: int, status: str) -> RestockingRequest:
    request = db.get(RestockingRequest, request_id)
    if request is None:
        raise IngredientNotFoundError
    request.status = status
    db.commit()
    db.refresh(request)
    return request


# --- Ch4 §4.8.4 algorithms -------------------------------------------------


def check_low_stock_threshold(
    db: Session, ingredient: Ingredient, default_threshold: Decimal | None = None
) -> bool:
    """ALGORITHM CheckLowStockThreshold (UC-IM-03). Returns True if an
    alert should fire for this ingredient right now.

    default_threshold lets a caller checking many ingredients look the
    system default up once instead of once per ingredient."""
    threshold = ingredient.low_stock_threshold
    if threshold is None:
        threshold = default_threshold
        if threshold is None:
            threshold = get_or_create_config(db).default_low_stock_threshold
    return ingredient.current_stock < threshold


def list_low_stock_ingredients(db: Session, *, limit: int = 100, offset: int = 0) -> list[Ingredient]:
    # Has to scan every ingredient to filter correctly (the threshold check
    # itself isn't a simple column comparison — see check_low_stock_threshold)
    # before paginating the filtered result, so this calls list_ingredients
    # with no limit rather than the paginated default.
    default_threshold = get_or_create_config(db).default_low_stock_threshold
    flagged = [i for i in list_ingredients(db) if check_low_stock_threshold(db, i, default_threshold)]
    return flagged[offset : offset + limit]


def check_near_expiry_batches(db: Session, *, today: date | None = None) -> dict:
    """ALGORITHM CheckNearExpiryBatches (UC-IM-05/UC-IM-08). Marks batches
    past their expiry date as 'expired' (feeding Module 6's waste
    aggregation once that exists in Sprint 3 — expiry_waste_events is
    returned here so Sprint 3 can wire it straight into CalculateWasteCost
    without touching this function) and flags batches inside the
    configured near-expiry window."""
    today = today or date.today()
    window_days = get_or_create_config(db).near_expiry_window_days

    active_batches = db.scalars(
        select(StockBatch).where(StockBatch.status == "active")
    ).all()

    near_expiry_alerts: list[dict] = []
    expiry_waste_events: list[dict] = []

    for batch in active_batches:
        days_remaining = (batch.expiry_date - today).days
        if days_remaining < 0:
            batch.status = "expired"
            expiry_waste_events.append(
                {
                    "ingredient_id": batch.ingredient_id,
                    "quantity": float(batch.quantity),
                    "source_type": "expiry",
                    "source_ref_id": batch.batch_id,
                }
            )
        elif days_remaining <= window_days:
            near_expiry_alerts.append(
                {
                    "batch_id": batch.batch_id,
                    "ingredient_id": batch.ingredient_id,
                    "expiry_date": batch.expiry_date.isoformat(),
                    "days_remaining": days_remaining,
                }
            )

    db.commit()
    return {"near_expiry_alerts": near_expiry_alerts, "expiry_waste_events": expiry_waste_events}


# --- FR3.1: consumption --------------------------------------------------


def _portions_consumed(db: Session, start: date, end: date) -> dict[int, Decimal]:
    """Portions of each menu item consumed between start and end inclusive.
    For each (item, meal period, day) the actual logged orders are used when
    there are any, and the forecast stands in where there aren't — FR3.1 /
    Form 2 describe stock as estimated from "logged deliveries and
    forecasted consumption", and a real order record is strictly better than
    the prediction it would otherwise be replaced by."""
    per_key: dict[tuple[int, str, date], Decimal] = {}
    for f in db.scalars(select(Forecast).where(Forecast.forecast_date.between(start, end))):
        per_key[(f.menu_item_id, f.meal_period, f.forecast_date)] = Decimal(f.predicted_quantity)

    for menu_item_id, meal_period, order_date, qty in db.execute(
        select(Order.menu_item_id, Order.meal_period, Order.order_date, func.sum(Order.quantity))
        .where(Order.order_date.between(start, end))
        .group_by(Order.menu_item_id, Order.meal_period, Order.order_date)
    ):
        per_key[(menu_item_id, meal_period, order_date)] = Decimal(qty)

    totals: dict[int, Decimal] = {}
    for (menu_item_id, _period, _day), qty in per_key.items():
        totals[menu_item_id] = totals.get(menu_item_id, Decimal("0")) + qty
    return totals


def apply_forecasted_consumption(db: Session, *, today: date | None = None) -> dict:
    """FR3.1 — deducts the ingredients consumed since the last run from
    current stock. Runs daily (see app/tasks/inventory_tasks.py) and only
    ever covers days that have fully ended, each exactly once, tracked by
    SystemConfig.stock_consumption_applied_through. The first ever run just
    starts the clock at yesterday instead of back-deducting history.

    Stock is floored at zero (a negative on-hand figure would just mean the
    recipes or order counts are off, and FR3.6 forbids negative stock), and
    Inventory Staff are alerted for any ingredient this pushes below its
    low-stock threshold."""
    today = today or date.today()
    through = today - timedelta(days=1)
    config = get_or_create_config(db)
    last = config.stock_consumption_applied_through

    if last is None:
        config.stock_consumption_applied_through = through
        db.commit()
        return {"initialised": True, "days_applied": 0, "ingredients_updated": 0, "low_stock_alerts": 0}
    if last >= through:
        return {"initialised": False, "days_applied": 0, "ingredients_updated": 0, "low_stock_alerts": 0}

    start = last + timedelta(days=1)
    default_threshold = config.default_low_stock_threshold
    low_before = {i.ingredient_id for i in list_ingredients(db) if check_low_stock_threshold(db, i, default_threshold)}

    portions = _portions_consumed(db, start, through)
    used: dict[int, Decimal] = {}
    if portions:
        links = db.scalars(select(RecipeIngredientLink).where(RecipeIngredientLink.menu_item_id.in_(portions)))
        for link in links:
            used[link.ingredient_id] = (
                used.get(link.ingredient_id, Decimal("0")) + portions[link.menu_item_id] * link.quantity_per_serving
            )

    for ingredient_id, quantity in used.items():
        ingredient = db.get(Ingredient, ingredient_id)
        if ingredient is None:
            continue
        ingredient.current_stock = max(Decimal("0"), ingredient.current_stock - quantity.quantize(Decimal("0.001")))

    config.stock_consumption_applied_through = through
    db.commit()

    newly_low = [
        i
        for i in list_ingredients(db)
        if i.ingredient_id not in low_before and check_low_stock_threshold(db, i, default_threshold)
    ]
    if newly_low:
        names = ", ".join(i.name for i in newly_low)
        notification_service.notify(
            db,
            recipient_role="Inventory Staff",
            type_="low_stock_alert",
            message=f"{len(newly_low)} ingredient(s) dropped below their low-stock threshold: {names}.",
        )

    return {
        "initialised": False,
        "days_applied": (through - last).days,
        "ingredients_updated": len(used),
        "low_stock_alerts": len(newly_low),
    }
