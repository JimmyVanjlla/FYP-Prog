"""Module 5: Kitchen Operations business logic. FR5.1-FR5.5."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import meal_periods
from app.models.kitchen import LeftoverLog, Notification, PrepConfirmation, PrepRecommendation
from app.models.menu import MenuItem
from app.schemas.kitchen import LeftoverLogCreate, PrepConfirmationCreate
from app.services import notifications as notification_service
from app.services import waste as waste_service
from app.services.config import get_or_create_config
from app.services.forecasting import get_latest_forecast


def _whole_portions(quantity) -> Decimal:
    """Portions are counted in whole dishes: 24.77 is prepared as 25, not 24.77."""
    return Decimal(str(quantity)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class NoForecastAvailableError(Exception):
    """FR5.1 — no forecast, and no manual_quantity fallback was given
    either (UC-KO-01 Alt Flow 3a)."""


class MenuItemInactiveError(Exception):
    """UC-MR-01 Alt Flow 3a — a deactivated item is removed from prep
    recommendation screens."""


class MealPeriodNotServedError(Exception):
    """The dish is not served in that meal period, so there is nothing to prep."""

    def __init__(self, dish: str, period: str):
        super().__init__(f"{dish} is not served at {period}.")


class RecommendationNotFoundError(Exception):
    pass


class DeviationReasonRequiredError(Exception):
    """FR5.5."""


class AlreadyConfirmedError(Exception):
    """A recommendation is confirmed once; confirming again would otherwise
    have hit the unique constraint and surfaced as a 500."""


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
    if not meal_periods.serves(item.meal_periods, meal_period):
        raise MealPeriodNotServedError(item.name, meal_period)

    forecast = get_latest_forecast(
        db, menu_item_id=menu_item_id, meal_period=meal_period, forecast_date=forecast_date
    )

    existing = db.scalars(
        select(PrepRecommendation)
        .where(PrepRecommendation.menu_item_id == menu_item_id)
        .where(PrepRecommendation.meal_period == meal_period)
        .where(PrepRecommendation.forecast_date == forecast_date)
    ).first()
    if existing is not None:
        # Forecasts are updated in place by each daily training run, and a
        # manual figure can be corrected, so an unconfirmed recommendation
        # follows whichever is current; once Kitchen Staff have confirmed
        # it, it's a record of what was shown and stays put.
        already_confirmed = (
            db.scalars(
                select(PrepConfirmation).where(PrepConfirmation.recommendation_id == existing.recommendation_id)
            ).first()
            is not None
        )
        if not already_confirmed:
            if forecast is not None:
                existing.forecast_id = forecast.forecast_id
                existing.recommended_quantity = _whole_portions(forecast.predicted_quantity)
            elif manual_quantity is not None:
                existing.forecast_id = None
                existing.recommended_quantity = _whole_portions(manual_quantity)
            db.commit()
            db.refresh(existing)
        return existing

    if forecast is None:
        if manual_quantity is None:
            raise NoForecastAvailableError
        recommendation = PrepRecommendation(
            menu_item_id=menu_item_id,
            forecast_id=None,
            meal_period=meal_period,
            forecast_date=forecast_date,
            recommended_quantity=_whole_portions(manual_quantity),
        )
        db.add(recommendation)
        db.commit()
        db.refresh(recommendation)
        return recommendation

    recommendation = PrepRecommendation(
        menu_item_id=menu_item_id,
        forecast_id=forecast.forecast_id,
        meal_period=meal_period,
        forecast_date=forecast_date,
        recommended_quantity=_whole_portions(forecast.predicted_quantity),
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
    db: Session,
    *,
    meal_period: str | None = None,
    menu_item_id: int | None = None,
    forecast_date: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PrepRecommendation]:
    """FR5.1/FR5.2 — Kitchen Staff need to see "today's prep
    recommendations" as a list; previously a recommendation was only ever
    visible in the single POST response that created it."""
    stmt = (
        select(PrepRecommendation)
        .order_by(PrepRecommendation.recommendation_id.desc())
        .limit(limit)
        .offset(offset)
    )
    if meal_period is not None:
        stmt = stmt.where(PrepRecommendation.meal_period == meal_period)
    if menu_item_id is not None:
        stmt = stmt.where(PrepRecommendation.menu_item_id == menu_item_id)
    if forecast_date is not None:
        stmt = stmt.where(PrepRecommendation.forecast_date == forecast_date)
    return list(db.scalars(stmt))


def confirmations_by_recommendation(
    db: Session, recommendation_ids: list[int]
) -> dict[int, PrepConfirmation]:
    """One query for all the confirmations a page of recommendations needs."""
    if not recommendation_ids:
        return {}
    rows = db.scalars(
        select(PrepConfirmation).where(PrepConfirmation.recommendation_id.in_(recommendation_ids))
    )
    return {c.recommendation_id: c for c in rows}


def confirm_prep(
    db: Session, *, staff_id: int, recommendation_id: int, data: PrepConfirmationCreate
) -> PrepConfirmation:
    """FR5.2 / FR5.5 — Kitchen Staff confirms or adjusts the recommended
    quantity; a reason is required when the adjustment exceeds
    SystemConfig.prep_deviation_threshold (%)."""
    recommendation = db.get(PrepRecommendation, recommendation_id)
    if recommendation is None:
        raise RecommendationNotFoundError
    if db.scalars(
        select(PrepConfirmation).where(PrepConfirmation.recommendation_id == recommendation_id)
    ).first() is not None:
        raise AlreadyConfirmedError

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


class NoPrepQuantityError(Exception):
    """A leftover percentage needs a prep quantity to be a percentage of."""


def _prepared_quantity_for(db: Session, *, menu_item_id: int, meal_period: str, day: date) -> Decimal | None:
    """How much of a dish was prepared for a meal period: what Kitchen Staff
    confirmed, else what was recommended. None if nothing was recorded."""
    recommendation = db.scalars(
        select(PrepRecommendation)
        .where(PrepRecommendation.menu_item_id == menu_item_id)
        .where(PrepRecommendation.meal_period == meal_period)
        .where(PrepRecommendation.forecast_date == day)
        .order_by(PrepRecommendation.recommendation_id.desc())
    ).first()
    if recommendation is None:
        return None
    confirmation = db.scalars(
        select(PrepConfirmation).where(PrepConfirmation.recommendation_id == recommendation.recommendation_id)
    ).first()
    quantity = confirmation.confirmed_quantity if confirmation is not None else recommendation.recommended_quantity
    return quantity if quantity > 0 else None


def log_leftover(db: Session, *, staff_id: int, data: LeftoverLogCreate) -> LeftoverLog:
    """FR5.3."""
    prepared, leftover, level = data.prepared_quantity, data.leftover_quantity, data.leftover_level
    if data.leftover_percent is not None:
        item = db.get(MenuItem, data.menu_item_id)
        if item is not None and not meal_periods.serves(item.meal_periods, data.meal_period):
            raise MealPeriodNotServedError(item.name, data.meal_period)
        prepared = _prepared_quantity_for(
            db, menu_item_id=data.menu_item_id, meal_period=data.meal_period, day=data.service_period_date
        )
        if prepared is None:
            raise NoPrepQuantityError
        leftover = (prepared * data.leftover_percent / 100).quantize(Decimal("0.01"))
        level = f"{data.leftover_percent}% left over"
    log = LeftoverLog(
        menu_item_id=data.menu_item_id,
        service_period_date=data.service_period_date,
        meal_period=data.meal_period,
        leftover_percent=data.leftover_percent,
        prepared_quantity=prepared,
        leftover_quantity=leftover,
        leftover_level=level,
        staff_id=staff_id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # FR6.1 — every leftover log immediately feeds Module 6's waste
    # aggregation (Algorithm CalculateWasteCost), not on a separate delay.
    waste_service.record_leftover_waste(db, log)
    return log


def list_leftover_logs(
    db: Session, *, menu_item_id: int | None = None, limit: int = 100, offset: int = 0
) -> list[LeftoverLog]:
    stmt = (
        select(LeftoverLog)
        .order_by(LeftoverLog.service_period_date.desc(), LeftoverLog.log_id.desc())
        .limit(limit)
        .offset(offset)
    )
    if menu_item_id is not None:
        stmt = stmt.where(LeftoverLog.menu_item_id == menu_item_id)
    return list(db.scalars(stmt))


def list_notifications(
    db: Session, *, recipient_id: int, limit: int = 100, offset: int = 0
) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.recipient_id == recipient_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
