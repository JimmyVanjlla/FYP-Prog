"""
Module 7: Portion & Forecast Feedback business logic. FR7.1-FR7.5, plus
ALGORITHM IdentifyHighLeftoverDishes (Ch4 §4.8.2 / UC-PF-03).
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.feedback import PortionRecommendation
from app.models.kitchen import LeftoverLog
from app.models.menu import RecipeIngredientLink
from app.services.config import get_or_create_config

DEFAULT_ANALYSIS_WINDOW_DAYS = 14
# How much to shrink the suggested portion by relative to the current one,
# when a dish is flagged — Ch4's pseudocode takes suggested_reduction as a
# given input without specifying its source, so this is the one concrete
# number that pseudocode leaves undefined; documented here rather than
# buried as a magic literal.
PORTION_REDUCTION_FACTOR = Decimal("0.90")


class RecommendationNotFoundError(Exception):
    pass


class InvalidPortionSizeError(Exception):
    pass


def compute_leftover_rate(
    db: Session, menu_item_id: int, *, today: date | None = None, analysis_window_days: int = DEFAULT_ANALYSIS_WINDOW_DAYS
) -> Decimal | None:
    """Steps 1-2 and the per-item ratio from ALGORITHM
    IdentifyHighLeftoverDishes, factored out so Module 4's forecasting
    pipeline can reuse the exact same signal for FR4.5 (see
    app/services/forecasting.py::_leftover_adjustment_factor) instead of
    duplicating the calculation. Returns None when there's no leftover
    data for the item in the window (nothing to compute a rate from)."""
    today = today or date.today()
    window_start = today - timedelta(days=analysis_window_days)
    logs = db.scalars(
        select(LeftoverLog)
        .where(LeftoverLog.menu_item_id == menu_item_id)
        .where(LeftoverLog.service_period_date >= window_start)
        .where(LeftoverLog.service_period_date <= today)
    ).all()
    total_prepared = sum((l.prepared_quantity for l in logs), Decimal("0"))
    if total_prepared == 0:
        return None
    total_leftover = sum((l.leftover_quantity for l in logs), Decimal("0"))
    return (total_leftover / total_prepared) * 100


def identify_high_leftover_dishes(
    db: Session, *, today: date | None = None, analysis_window_days: int = DEFAULT_ANALYSIS_WINDOW_DAYS
) -> list[PortionRecommendation]:
    """ALGORITHM IdentifyHighLeftoverDishes."""
    today = today or date.today()
    window_start = today - timedelta(days=analysis_window_days)
    threshold = get_or_create_config(db).leftover_rate_threshold

    # Step 1-2: fetch and group window_logs by menu_item_id.
    window_logs = db.scalars(
        select(LeftoverLog)
        .where(LeftoverLog.service_period_date >= window_start)
        .where(LeftoverLog.service_period_date <= today)
    ).all()
    by_item: dict[int, list[LeftoverLog]] = {}
    for log in window_logs:
        by_item.setdefault(log.menu_item_id, []).append(log)

    # Step 3.
    pending_by_item: dict[int, PortionRecommendation] = {
        r.menu_item_id: r
        for r in db.scalars(select(PortionRecommendation).where(PortionRecommendation.status == "pending"))
    }

    flagged: list[PortionRecommendation] = []
    items_with_logs = set(by_item.keys())

    # Steps 4-13.
    for menu_item_id, logs in by_item.items():
        total_prepared = sum((l.prepared_quantity for l in logs), Decimal("0"))
        total_leftover = sum((l.leftover_quantity for l in logs), Decimal("0"))
        if total_prepared == 0:
            continue
        leftover_rate = (total_leftover / total_prepared) * 100

        existing = pending_by_item.get(menu_item_id)
        if leftover_rate > threshold:
            suggested_size = _suggest_portion_size(db, menu_item_id)
            if existing is not None:
                existing.leftover_rate = leftover_rate
                existing.suggested_portion_size = suggested_size
                flagged.append(existing)
            else:
                recommendation = PortionRecommendation(
                    menu_item_id=menu_item_id,
                    leftover_rate=leftover_rate,
                    suggested_portion_size=suggested_size,
                    status="pending",
                )
                db.add(recommendation)
                flagged.append(recommendation)

    # Step 14-15 — UC-PF-03 Alt Flow 3a: a dish that used to be flagged but
    # is no longer over threshold has its pending recommendation withdrawn.
    for menu_item_id, existing in pending_by_item.items():
        if menu_item_id in items_with_logs and menu_item_id not in {
            f.menu_item_id for f in flagged
        }:
            db.delete(existing)

    db.commit()
    for f in flagged:
        db.refresh(f)
    return flagged


def _suggest_portion_size(db: Session, menu_item_id: int) -> Decimal:
    """Bases the suggestion on the dish's current largest recipe
    ingredient quantity as a stand-in "portion size" (Ch4's dictionary has
    no single MenuItem.portion_size field — portion size is expressed
    per-ingredient via RecipeIngredientLink.quantity_per_serving, so there
    isn't one scalar to shrink; this picks the first linked ingredient's
    quantity as a representative figure for display purposes only. FR7.3's
    actual effect — approval scaling every linked ingredient down — doesn't
    depend on this being exact.)"""
    link = db.scalars(
        select(RecipeIngredientLink)
        .where(RecipeIngredientLink.menu_item_id == menu_item_id)
        .order_by(RecipeIngredientLink.link_id)
    ).first()
    if link is None:
        return Decimal("0")
    return (link.quantity_per_serving * PORTION_REDUCTION_FACTOR).quantize(Decimal("0.001"))


def list_portion_recommendations(db: Session, *, status: str | None = None) -> list[PortionRecommendation]:
    stmt = select(PortionRecommendation).order_by(PortionRecommendation.created_at.desc())
    if status is not None:
        stmt = stmt.where(PortionRecommendation.status == status)
    return list(db.scalars(stmt))


def approve_portion_recommendation(db: Session, recommendation_id: int) -> PortionRecommendation:
    """FR2.3/FR7.2/FR7.3 — Manager approval propagates the reduction
    factor to every ingredient in the dish's recipe (scaling each
    quantity_per_serving down, not just the one representative figure
    computed above), so the actual serving really does shrink across the
    board — this is also what satisfies FR2.3's "portion size adjustments
    approved by the Restaurant Manager... automatically update ingredient
    quantities per serving across all related modules", just filed under
    Module 7 rather than Module 2 since that's where the approval action
    lives.

    FR7.4/FR4.5's forecast refinement is a *separate* mechanism, not a
    side-effect of this function: quantity_per_serving only affects
    ingredient consumption per order, not the order COUNT Prophet trains
    on, so there's no "next training cycle just picks it up for free" the
    way an earlier version of this comment claimed. The actual downward
    pull happens in app/services/forecasting.py's
    _leftover_adjustment_factor, applied at forecast-generation time using
    the same leftover_rate signal computed here (see
    compute_leftover_rate) — not by tagging Order rows, since Ch4's
    33-entity dictionary has no column for that (Order only has
    order_id/menu_item_id/quantity/meal_period/order_date)."""
    recommendation = db.get(PortionRecommendation, recommendation_id)
    if recommendation is None:
        raise RecommendationNotFoundError
    if recommendation.status != "pending":
        raise InvalidPortionSizeError

    links = db.scalars(
        select(RecipeIngredientLink).where(RecipeIngredientLink.menu_item_id == recommendation.menu_item_id)
    ).all()
    for link in links:
        link.quantity_per_serving = (link.quantity_per_serving * PORTION_REDUCTION_FACTOR).quantize(
            Decimal("0.001")
        )

    recommendation.status = "approved"
    db.commit()
    db.refresh(recommendation)
    return recommendation


def reject_portion_recommendation(db: Session, recommendation_id: int) -> PortionRecommendation:
    recommendation = db.get(PortionRecommendation, recommendation_id)
    if recommendation is None:
        raise RecommendationNotFoundError
    recommendation.status = "rejected"
    db.commit()
    db.refresh(recommendation)
    return recommendation
