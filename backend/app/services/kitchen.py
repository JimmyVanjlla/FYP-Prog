"""Module 5: Kitchen Operations business logic. FR5.1-FR5.5."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kitchen import LeftoverLog, Notification, PrepConfirmation, PrepRecommendation
from app.schemas.kitchen import LeftoverLogCreate, PrepConfirmationCreate
from app.services import notifications as notification_service
from app.services import waste as waste_service
from app.services.config import get_or_create_config
from app.services.forecasting import get_latest_forecast


class NoForecastAvailableError(Exception):
    """FR5.1 — nothing to base a recommendation on yet."""


class RecommendationNotFoundError(Exception):
    pass


class DeviationReasonRequiredError(Exception):
    """FR5.5."""


def generate_prep_recommendation(
    db: Session, *, menu_item_id: int, meal_period: str, forecast_date: date
) -> PrepRecommendation:
    """FR5.1 — one recommendation per (menu_item, meal_period, forecast_date),
    reusing an existing one if already generated rather than duplicating."""
    forecast = get_latest_forecast(
        db, menu_item_id=menu_item_id, meal_period=meal_period, forecast_date=forecast_date
    )
    if forecast is None:
        raise NoForecastAvailableError

    existing_reco = db.scalars(
        select(PrepRecommendation).where(PrepRecommendation.forecast_id == forecast.forecast_id)
    ).first()
    if existing_reco is not None:
        return existing_reco

    recommendation = PrepRecommendation(
        menu_item_id=menu_item_id,
        forecast_id=forecast.forecast_id,
        meal_period=meal_period,
        recommended_quantity=forecast.predicted_quantity,
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    return recommendation


def confirm_prep(
    db: Session, *, staff_id: int, recommendation_id: int, data: PrepConfirmationCreate
) -> PrepConfirmation:
    """FR5.2 / FR5.5 — Kitchen Staff confirms or adjusts the recommended
    quantity; a reason is required when the adjustment exceeds
    SystemConfig.prep_deviation_threshold (%)."""
    recommendation = db.get(PrepRecommendation, recommendation_id)
    if recommendation is None:
        raise RecommendationNotFoundError

    recommended = recommendation.recommended_quantity
    deviation_pct = (
        abs(data.confirmed_quantity - recommended) / recommended * 100 if recommended else Decimal(0)
    )
    threshold = get_or_create_config(db).prep_deviation_threshold
    if deviation_pct > threshold and not data.deviation_reason:
        raise DeviationReasonRequiredError

    confirmation = PrepConfirmation(
        recommendation_id=recommendation_id,
        confirmed_quantity=data.confirmed_quantity,
        deviation_reason=data.deviation_reason,
        staff_id=staff_id,
    )
    db.add(confirmation)
    db.commit()
    db.refresh(confirmation)

    # FR5.4 — notify on a significant prep change, not on every routine
    # confirmation that matches the recommendation.
    if deviation_pct > threshold:
        notification_service.notify(
            db,
            recipient_role="Kitchen Staff",
            type_="prep_update",
            message=(
                f"Prep quantity for recommendation #{recommendation_id} adjusted "
                f"to {data.confirmed_quantity} ({deviation_pct:.1f}% deviation)."
            ),
        )
    return confirmation


def log_leftover(db: Session, *, staff_id: int, data: LeftoverLogCreate) -> LeftoverLog:
    """FR5.3."""
    log = LeftoverLog(
        menu_item_id=data.menu_item_id,
        service_period_date=data.service_period_date,
        prepared_quantity=data.prepared_quantity,
        leftover_quantity=data.leftover_quantity,
        leftover_level=data.leftover_level,
        staff_id=staff_id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # FR6.1 — every leftover log immediately feeds Module 6's waste
    # aggregation (Algorithm CalculateWasteCost), not on a separate delay.
    waste_service.record_leftover_waste(db, log)
    return log


def list_leftover_logs(db: Session, *, menu_item_id: int | None = None) -> list[LeftoverLog]:
    stmt = select(LeftoverLog).order_by(LeftoverLog.service_period_date.desc())
    if menu_item_id is not None:
        stmt = stmt.where(LeftoverLog.menu_item_id == menu_item_id)
    return list(db.scalars(stmt))


def list_notifications(db: Session, *, recipient_id: int) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.recipient_id == recipient_id)
            .order_by(Notification.created_at.desc())
        )
    )
