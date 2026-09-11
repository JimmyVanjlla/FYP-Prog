from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.feedback import IdentifyHighLeftoverResult, PortionRecommendationOut
from app.services import feedback as feedback_service

router = APIRouter(prefix="/portion-feedback", tags=["portion-feedback"])


@router.get("/recommendations", response_model=list[PortionRecommendationOut])
def list_recommendations(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> list[PortionRecommendationOut]:
    """FR7.2."""
    return feedback_service.list_portion_recommendations(db, status=status_filter)


@router.post("/analyze", response_model=IdentifyHighLeftoverResult)
def trigger_analysis(
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> IdentifyHighLeftoverResult:
    """FR7.1 — manual on-demand trigger; runs automatically via Celery Beat
    otherwise (see app/tasks/feedback_tasks.py)."""
    flagged = feedback_service.identify_high_leftover_dishes(db)
    return IdentifyHighLeftoverResult(flagged_count=len(flagged))


@router.post("/recommendations/{recommendation_id}/approve", response_model=PortionRecommendationOut)
def approve_recommendation(
    recommendation_id: int,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> PortionRecommendationOut:
    """FR7.2 / FR7.3."""
    try:
        return feedback_service.approve_portion_recommendation(db, recommendation_id)
    except feedback_service.RecommendationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")
    except feedback_service.InvalidPortionSizeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only pending recommendations can be approved.",
        )


@router.post("/recommendations/{recommendation_id}/reject", response_model=PortionRecommendationOut)
def reject_recommendation(
    recommendation_id: int,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> PortionRecommendationOut:
    try:
        return feedback_service.reject_portion_recommendation(db, recommendation_id)
    except feedback_service.RecommendationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")
