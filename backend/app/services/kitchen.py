"""Module 5: Kitchen Operations business logic. FR5.1-FR5.5."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kitchen import LeftoverLog, Notification, PrepConfirmation, PrepRecommendation
from app.models.menu import MenuItem
from app.schemas.kitchen import LeftoverLogCreate, PrepConfirmationCreate
from app.services import notifications as notification_service
from app.services import waste as waste_service
from app.services.config import get_or_create_config
from app.services.forecasting import get_latest_forecast


class NoForecastAvailableError(Exception):
    """FR5.1 — no forecast, and no manual_quantity fallback was given
    either (UC-KO-01 Alt Flow 3a)."""


class MenuItemInactiveError(Exception):
    """UC-MR-01 Alt Flow 3a — a deactivated item is removed from prep
    recommendation screens."""


class RecommendationNotFoundError(Exception):
    pass


class DeviationReasonRequiredError(Exception):
    """FR5.5."""


def generate_prep_recommendation(
    db: Session,
    *,
    menu_item_id: int,
    meal_period: str,
    forecast_date: date,
    manual_quantity=None,
) -> PrepRecommendation:
    """FR5.1 — one recommendation per (menu_item, meal_period, forecast_date),
    reusing an existing one if already generated rather than duplicating.

    UC-KO-01 Alt Flow 3a — when no forecast exists yet, manual_quantity
    (if given) creates a manual recommendation instead of dead-ending;
    forecast_id is left null on that row (see the model's docstring for
    why that's a deliberate, documented divergence from Ch4's dictionary)."""
    item = db.get(MenuItem, menu_item_id)
    if item is None or not item.is_active:
        raise MenuItemInactiveError

    forecast = get_latest_forecast(
        db, menu_item_id=menu_item_id, meal_period=meal_period, forecast_date=forecast_date
    )
    if forecast is None:
        if manual_quantity is None:
            raise NoForecastAvailableError
        recommendation = PrepRecommendation(
            menu_item_id=menu_item_id,
            forecast_id=None,
            meal_period=meal_period,
            recommended_quantity=manual_quantity,
        )
        db.add(recommendation)
        db.commit()
        db.refresh(recommendation)
        return recommendation

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
    # FR5.4 / UC-KO-04 main flow step 1 — "an update to prep quantity
    # recommendations following a new forecast cycle". Recommendations
    # here are generated on request rather than automatically the moment
    # training finishes, so "new" is scoped to this call producing a
    # recommendation that didn't already exist (the `existing_reco` early
    # return above is deliberately excluded from this notification).
    notification_service.notify(
        db,
        recipient_role="Kitchen Staff",
        type_="prep_update",
        message=f"New prep recommendation for menu item #{menu_item_id} ({meal_period}, "
        f"{forecast_date}): {recommendation.recommended_quantity} portions.",
    )
    return recommendation


def list_prep_recommendations(
    db: Session, *, meal_period: str | None = None, menu_item_id: int | None = None
) -> list[PrepRecommendation]:
    """FR5.1/FR5.2 — Kitchen Staff need to see "today's prep
    recommendations" as a list; previously a recommendation was only ever
    visible in the single POST response that created it."""
    stmt = select(PrepRecommendation).order_by(PrepRecommendation.recommendation_id.desc())
    if meal_period is not None:
        stmt = stmt.where(PrepRecommendation.meal_period == meal_period)
    if menu_item_id is not None:
        stmt = stmt.where(PrepRecommendation.menu_item_id == menu_item_id)
    return list(db.scalars(stmt))


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
