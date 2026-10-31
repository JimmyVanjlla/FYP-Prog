from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
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


def _prep_out(db: Session, recommendations: list) -> list[PrepRecommendationOut]:
    """Adds each recommendation's confirmation (if Kitchen Staff have
    already confirmed it) so a client can tell what's still to do."""
    confirmations = kitchen_service.confirmations_by_recommendation(
        db, [r.recommendation_id for r in recommendations]
    )
    out: list[PrepRecommendationOut] = []
    for r in recommendations:
        item = PrepRecommendationOut.model_validate(r)
        confirmation = confirmations.get(r.recommendation_id)
        if confirmation is not None:
            item.confirmed = True
            item.confirmed_quantity = confirmation.confirmed_quantity
            item.deviation_reason = confirmation.deviation_reason
        out.append(item)
    return out


@router.get("/prep-recommendations", response_model=list[PrepRecommendationOut])
def list_prep_recommendations(
    meal_period: str | None = None,
    menu_item_id: int | None = None,
    forecast_date: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[PrepRecommendationOut]:
    """FR5.1/FR5.2 — the read side; previously a recommendation was only
    ever visible in the single POST response that created it."""
    return _prep_out(
        db,
        kitchen_service.list_prep_recommendations(
            db,
            meal_period=meal_period,
            menu_item_id=menu_item_id,
            forecast_date=forecast_date,
            limit=limit,
            offset=offset,
        ),
    )


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
        recommendation = kitchen_service.generate_prep_recommendation(
            db,
            menu_item_id=data.menu_item_id,
            meal_period=data.meal_period,
            forecast_date=data.forecast_date,
            manual_quantity=data.manual_quantity,
        )
        return _prep_out(db, [recommendation])[0]
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
    except kitchen_service.AlreadyConfirmedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This prep quantity has already been confirmed."
        )
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
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[LeftoverLogOut]:
    return kitchen_service.list_leftover_logs(db, menu_item_id=menu_item_id, limit=limit, offset=offset)


@router.get("/notifications", response_model=list[NotificationOut])
def list_my_notifications(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    """FR5.4."""
    return kitchen_service.list_notifications(db, recipient_id=user.user_id, limit=limit, offset=offset)
