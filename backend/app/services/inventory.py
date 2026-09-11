"""Module 3: Inventory Management business logic. FR3.1-FR3.6, plus
Algorithm "CheckLowStockThreshold" and "CheckNearExpiryBatches" (Ch4
§4.8.4)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import Ingredient, RestockingRequest, StockAdjustment, StockBatch
from app.schemas.inventory import IngredientCreate, RestockingRequestCreate, StockAdjustmentCreate, StockBatchCreate
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


def list_ingredients(db: Session) -> list[Ingredient]:
    return list(db.scalars(select(Ingredient).order_by(Ingredient.name)))


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


def list_restocking_requests(db: Session, *, status: str | None = None) -> list[RestockingRequest]:
    stmt = select(RestockingRequest).order_by(RestockingRequest.urgency.desc())
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


def check_low_stock_threshold(db: Session, ingredient: Ingredient) -> bool:
    """ALGORITHM CheckLowStockThreshold (UC-IM-03). Returns True if an
    alert should fire for this ingredient right now."""
    threshold = ingredient.low_stock_threshold
    if threshold is None:
        threshold = get_or_create_config(db).default_low_stock_threshold
    return ingredient.current_stock < threshold


def list_low_stock_ingredients(db: Session) -> list[Ingredient]:
    return [i for i in list_ingredients(db) if check_low_stock_threshold(db, i)]


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
