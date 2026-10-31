from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.inventory import (
    ConsumptionApplyResult,
    IngredientCreate,
    IngredientOut,
    RestockingRequestCreate,
    RestockingRequestOut,
    RestockingRequestStatusUpdate,
    StockAdjustmentCreate,
    StockAdjustmentOut,
    StockBatchCreate,
    StockBatchOut,
    ThresholdUpdate,
)
from app.services import inventory as inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])

_INVENTORY_WRITE_ROLES = (Role.INVENTORY_STAFF, Role.RESTAURANT_MANAGER)


def _ingredient_out(ingredient, db: Session) -> IngredientOut:
    out = IngredientOut.model_validate(ingredient)
    out.is_low_stock = inventory_service.check_low_stock_threshold(db, ingredient)
    return out


@router.get("/ingredients", response_model=list[IngredientOut])
def list_ingredients(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[IngredientOut]:
    items = inventory_service.list_ingredients(db, limit=limit, offset=offset)
    return [_ingredient_out(i, db) for i in items]


@router.get("/ingredients/low-stock", response_model=list[IngredientOut])
def list_low_stock(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[IngredientOut]:
    """FR3.3 threshold check, surfaced as its own endpoint since it's the
    one Kitchen/Manager dashboards actually poll (Ch4 §4.4.1 severity-list
    UI pattern)."""
    items = inventory_service.list_low_stock_ingredients(db, limit=limit, offset=offset)
    return [_ingredient_out(i, db) for i in items]


@router.post("/ingredients", response_model=IngredientOut, status_code=status.HTTP_201_CREATED)
def create_ingredient(
    data: IngredientCreate,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_INVENTORY_WRITE_ROLES)),
) -> IngredientOut:
    return _ingredient_out(inventory_service.create_ingredient(db, data), db)


@router.patch("/ingredients/{ingredient_id}/threshold", response_model=IngredientOut)
def update_threshold(
    ingredient_id: int,
    data: ThresholdUpdate,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_INVENTORY_WRITE_ROLES)),
) -> IngredientOut:
    """FR3.3."""
    try:
        ingredient = inventory_service.set_low_stock_threshold(
            db, ingredient_id, data.low_stock_threshold
        )
    except inventory_service.IngredientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found.")
    return _ingredient_out(ingredient, db)


@router.get("/stock-adjustments", response_model=list[StockAdjustmentOut])
def list_stock_adjustments(
    ingredient_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[StockAdjustmentOut]:
    """FR3.4 — adjustment history, viewable rather than write-only."""
    return inventory_service.list_stock_adjustments(
        db, ingredient_id=ingredient_id, limit=limit, offset=offset
    )


@router.post(
    "/stock-adjustments", response_model=StockAdjustmentOut, status_code=status.HTTP_201_CREATED
)
def record_stock_adjustment(
    data: StockAdjustmentCreate,
    db: Session = Depends(get_db),
    staff: User = Depends(require_role(*_INVENTORY_WRITE_ROLES)),
) -> StockAdjustmentOut:
    """FR3.4 / FR3.6."""
    try:
        return inventory_service.record_stock_adjustment(db, staff.user_id, data)
    except inventory_service.IngredientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found.")
    except inventory_service.StockWouldGoNegativeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This adjustment would drive stock below zero.",
        )


@router.get("/stock-batches", response_model=list[StockBatchOut])
def list_stock_batches(
    ingredient_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[StockBatchOut]:
    """FR3.2 — batch/expiry tracking needs to be viewable, not just
    logged."""
    return inventory_service.list_stock_batches(
        db, ingredient_id=ingredient_id, limit=limit, offset=offset
    )


@router.post("/stock-batches", response_model=StockBatchOut, status_code=status.HTTP_201_CREATED)
def record_stock_batch(
    data: StockBatchCreate,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_INVENTORY_WRITE_ROLES)),
) -> StockBatchOut:
    """FR3.1 / FR3.2."""
    try:
        return inventory_service.record_stock_batch(db, data)
    except inventory_service.IngredientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found.")


@router.post(
    "/restocking-requests",
    response_model=RestockingRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_restocking_request(
    data: RestockingRequestCreate,
    db: Session = Depends(get_db),
    staff: User = Depends(require_role(Role.KITCHEN_STAFF)),
) -> RestockingRequestOut:
    """FR3.5."""
    try:
        return inventory_service.create_restocking_request(db, staff.user_id, data)
    except inventory_service.IngredientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found.")


@router.get("/restocking-requests", response_model=list[RestockingRequestOut])
def list_restocking_requests(
    status_filter: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_INVENTORY_WRITE_ROLES)),
) -> list[RestockingRequestOut]:
    return inventory_service.list_restocking_requests(
        db, status=status_filter, limit=limit, offset=offset
    )


@router.patch("/restocking-requests/{request_id}", response_model=RestockingRequestOut)
def update_restocking_request(
    request_id: int,
    data: RestockingRequestStatusUpdate,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_INVENTORY_WRITE_ROLES)),
) -> RestockingRequestOut:
    try:
        return inventory_service.update_restocking_request_status(db, request_id, data.status)
    except inventory_service.IngredientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")


@router.post("/consumption/apply", response_model=ConsumptionApplyResult)
def apply_consumption(
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_INVENTORY_WRITE_ROLES)),
) -> ConsumptionApplyResult:
    """FR3.1 — manual trigger for the daily stock-consumption job (it runs
    automatically via Celery Beat; this is for catching up on demand)."""
    return ConsumptionApplyResult(**inventory_service.apply_forecasted_consumption(db))
