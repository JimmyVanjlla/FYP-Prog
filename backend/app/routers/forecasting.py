from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.forecasting import ForecastOut, ForecastTrainingResult, OrderCreate, OrderOut
from app.services import forecasting as forecasting_service

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


@router.post("/orders", response_model=OrderOut, status_code=201)
def record_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> OrderOut:
    return forecasting_service.record_order(db, data)


@router.get("/forecasts", response_model=list[ForecastOut])
def list_forecasts(
    menu_item_id: int | None = None,
    meal_period: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ForecastOut]:
    """FR4.3 — surfaced to any authenticated role; stored forecast rows are
    returned as-is, no reprocessing on query."""
    return forecasting_service.list_forecasts(db, menu_item_id=menu_item_id, meal_period=meal_period)


@router.post("/train", response_model=ForecastTrainingResult)
def trigger_training(
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> ForecastTrainingResult:
    """Manual on-demand trigger for Algorithm 1 (Ch4 §4.8.1) — in normal
    operation this runs automatically via Celery Beat (see
    app/tasks/forecasting_tasks.py), but a Manager can force a re-run
    rather than waiting for the next scheduled 06:00 pass."""
    result = forecasting_service.train_and_generate_forecasts(db, today=date.today())
    return ForecastTrainingResult(**result)
