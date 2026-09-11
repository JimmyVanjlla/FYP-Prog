from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.kitchen import (
    LeftoverLogCreate,
    LeftoverLogOut,
    NotificationOut,
    PrepConfirmationCreate,
    PrepConfirmationOut,
    PrepRecommendationOut,
    PrepRecommendationRequest,
)
from app.services import kitchen as kitchen_service

router = APIRouter(prefix="/kitchen", tags=["kitchen"])


@router.get("/prep-recommendations", response_model=list[PrepRecommendationOut])
def list_prep_recommendations(
    meal_period: str | None = None,
    menu_item_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[PrepRecommendationOut]:
    """FR5.1/FR5.2 — the read side; previously a recommendation was only
    ever visible in the single POST response that created it."""
    return kitchen_service.list_prep_recommendations(db, meal_period=meal_period, menu_item_id=menu_item_id)


@router.post(
    "/prep-recommendations", response_model=PrepRecommendationOut, status_code=status.HTTP_201_CREATED
)
def generate_prep_recommendation(
    data: PrepRecommendationRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PrepRecommendationOut:
    """FR5.1 / UC-KO-01 Alt Flow 3a."""
    try:
        return kitchen_service.generate_prep_recommendation(
            db,
            menu_item_id=data.menu_item_id,
            meal_period=data.meal_period,
            forecast_date=data.forecast_date,
            manual_quantity=data.manual_quantity,
        )
    except kitchen_service.MenuItemInactiveError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found or inactive.")
    except kitchen_service.NoForecastAvailableError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No forecast available yet for this item/meal period/date. "
            "Provide manual_quantity to enter a prep quantity manually.",
        )


@router.post(
    "/prep-recommendations/{recommendation_id}/confirm",
    response_model=PrepConfirmationOut,
    status_code=status.HTTP_201_CREATED,
)
def confirm_prep(
    recommendation_id: int,
    data: PrepConfirmationCreate,
    db: Session = Depends(get_db),
    staff: User = Depends(require_role(Role.KITCHEN_STAFF)),
) -> PrepConfirmationOut:
    """FR5.2 / FR5.5."""
    try:
        return kitchen_service.confirm_prep(
            db, staff_id=staff.user_id, recommendation_id=recommendation_id, data=data
        )
    except kitchen_service.RecommendationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")
    except kitchen_service.DeviationReasonRequiredError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A reason is required when the confirmed quantity deviates "
            "from the recommendation beyond the configured threshold.",
        )


@router.post("/leftover-logs", response_model=LeftoverLogOut, status_code=status.HTTP_201_CREATED)
def log_leftover(
    data: LeftoverLogCreate,
    db: Session = Depends(get_db),
    staff: User = Depends(require_role(Role.KITCHEN_STAFF)),
) -> LeftoverLogOut:
    """FR5.3."""
    return kitchen_service.log_leftover(db, staff_id=staff.user_id, data=data)


@router.get("/leftover-logs", response_model=list[LeftoverLogOut])
def list_leftover_logs(
    menu_item_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[LeftoverLogOut]:
    return kitchen_service.list_leftover_logs(db, menu_item_id=menu_item_id)


@router.get("/notifications", response_model=list[NotificationOut])
def list_my_notifications(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[NotificationOut]:
    """FR5.4."""
    return kitchen_service.list_notifications(db, recipient_id=user.user_id)
