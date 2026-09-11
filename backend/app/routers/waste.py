from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.waste import WasteLogOut, WasteReductionTrendOut, WasteTrendRequest
from app.services import waste as waste_service

router = APIRouter(prefix="/waste", tags=["waste"])


@router.get("/logs", response_model=list[WasteLogOut])
def list_waste_logs(
    ingredient_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[WasteLogOut]:
    """FR6.1."""
    return waste_service.list_waste_logs(db, ingredient_id=ingredient_id)


@router.get("/trends", response_model=list[WasteReductionTrendOut])
def list_waste_trends(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[WasteReductionTrendOut]:
    """FR6.3."""
    return waste_service.list_waste_trends(db)


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
