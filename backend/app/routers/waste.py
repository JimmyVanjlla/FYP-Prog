from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.waste import WasteLogCreate, WasteLogOut, WasteReductionTrendOut, WasteTrendRequest
from app.services import waste as waste_service

router = APIRouter(prefix="/waste", tags=["waste"])


@router.get("/logs", response_model=list[WasteLogOut])
def list_waste_logs(
    ingredient_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[WasteLogOut]:
    """FR6.1."""
    return waste_service.list_waste_logs(db, ingredient_id=ingredient_id, limit=limit, offset=offset)


@router.post("/logs", response_model=WasteLogOut, status_code=status.HTTP_201_CREATED)
def create_waste_log(
    data: WasteLogCreate,
    db: Session = Depends(get_db),
    _staff: User = Depends(
        require_role(Role.KITCHEN_STAFF, Role.INVENTORY_STAFF, Role.RESTAURANT_MANAGER)
    ),
) -> WasteLogOut:
    """FR6.1 / FR6.5 — Kitchen Staff log leftover waste and Inventory Staff
    log expiry waste; entries are validated against what was prepared or
    delivered."""
    try:
        return waste_service.create_manual_waste_log(db, data)
    except waste_service.InvalidWasteEntryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/trends", response_model=list[WasteReductionTrendOut])
def list_waste_trends(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[WasteReductionTrendOut]:
    """FR6.3."""
    return waste_service.list_waste_trends(db, limit=limit, offset=offset)


@router.post("/trends", response_model=WasteReductionTrendOut, status_code=201)
def generate_waste_trend(
    data: WasteTrendRequest,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> WasteReductionTrendOut:
    """FR6.3 — Manager triggers a rollup for a given period (e.g. the past
    week) to chart on the waste reduction dashboard."""
    return waste_service.aggregate_waste_reduction_trend(
        db, period_start=data.period_start, period_end=data.period_end
    )
