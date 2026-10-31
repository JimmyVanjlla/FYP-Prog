"""
Module 4: Demand Forecasting business logic.

Implements Algorithm 1 (Ch4 §4.8.1, "TrainAndGenerateForecast" —
UC-DF-02 / FR4.1-FR4.6) as close to the pseudocode as SQLAlchemy + pandas +
Prophet allow. Forecasts are trained per (menu_item_id, meal_period) pair —
Ch4's pseudocode says "FOR EACH menu_item", but the Forecast entity itself
is keyed by (menu_item_id, meal_period, forecast_date) and FR4.1 explicitly
says orders are "aggregated by menu item, meal period, and date", so a
separate model is trained per item/meal-period combination (breakfast,
lunch, and dinner demand for the same dish don't follow the same curve).

FR4.5's leftover-feedback refinement is applied as a post-hoc downward
scale on Prophet's raw output — see _leftover_adjustment_factor below —
rather than by feeding leftover data into Prophet itself as a regressor,
since the leftover signal only exists per dish, not per the date-indexed
order series Prophet actually fits.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.forecasting import Forecast, ForecastAccuracy, Order
from app.models.menu import MenuItem
from app.services import notifications as notification_service
from app.services.config import get_or_create_config
from app.services.feedback import compute_leftover_rate

# UC-DF-02 Alt Flow 2a — below this many historical (date, meal_period)
# data points for an item, Prophet is skipped and the item is flagged
# rather than forced through a fit that would overfit noise.
MIN_DATA_POINTS = 14
# FR5.4 / UC-KO-04 — how far above an item/meal_period's own historical
# average a new forecast has to be before it's treated as a "high-demand"
# spike worth alerting Kitchen Staff about. Ch4 doesn't name an exact
# figure ("exceeding a configured threshold"), so this is a documented,
# reasonable default rather than a transcribed report value.
HIGH_DEMAND_MULTIPLIER = 1.5
# How many days ahead each training run forecasts.
FORECAST_HORIZON_DAYS = 7


def _leftover_adjustment_factor(db: Session, menu_item_id: int, *, today: date) -> float:
    """FR4.5 — "incorporate leftover feedback data to refine Prophet
    forecast outputs downward for persistently over-forecasted dishes."

    Reuses Module 7's exact leftover_rate signal (FR7.1) rather than a
    second metric: when a dish's leftover rate exceeds
    SystemConfig.leftover_rate_threshold, its raw Prophet prediction is
    scaled down by that same rate (a dish running 30% leftover gets its
    forecast cut by 30%), directly pulling the forecast toward what's
    actually being consumed. Below threshold, or with no leftover data
    yet, the raw Prophet estimate is used unadjusted (factor of 1.0).

    This is deliberately a separate mechanism from FR7.3's portion-size
    reduction (RecipeIngredientLink.quantity_per_serving) — that ratio
    only affects ingredient consumption per order, not the order COUNT
    this module forecasts, so it can't do FR4.5's job on its own. See
    app/services/feedback.py::approve_portion_recommendation for the same
    point made from the other side."""
    rate = compute_leftover_rate(db, menu_item_id, today=today)
    if rate is None:
        return 1.0
    threshold = get_or_create_config(db).leftover_rate_threshold
    if rate <= threshold:
        return 1.0
    return max(0.0, 1.0 - float(rate) / 100)


class InsufficientDataError(Exception):
    """Raised per-item internally; callers of train_and_generate_forecasts
    don't see this directly — see `skipped` in its return value instead."""


def _load_grouped_orders(db: Session) -> pd.DataFrame:
    """Step 1-2 of Algorithm 1: fetch all orders, group by
    (menu_item_id, meal_period, date), aggregate quantity as the daily
    order count (Prophet's `y`), date as `ds`."""
    rows = db.execute(
        select(Order.menu_item_id, Order.meal_period, Order.order_date, Order.quantity)
    ).all()
    if not rows:
        return pd.DataFrame(columns=["menu_item_id", "meal_period", "ds", "y"])

    raw = pd.DataFrame(rows, columns=["menu_item_id", "meal_period", "order_date", "quantity"])
    grouped = (
        raw.groupby(["menu_item_id", "meal_period", "order_date"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"order_date": "ds", "quantity": "y"})
    )
    grouped["ds"] = pd.to_datetime(grouped["ds"])
    return grouped


def train_and_generate_forecasts(
    db: Session, *, today: date | None = None
) -> dict:
    """Runs Algorithm 1 for every (menu_item_id, meal_period) pair with
    enough history, storing Forecast rows and backfilling ForecastAccuracy
    for any past forecast that now has a matching actual order. Returns a
    summary dict rather than raising, since a Celery Beat run covering many
    items shouldn't abort partway through one item's failure."""
    # Imported here, not at module load, so the rest of the backend can
    # boot and be tested even in an environment where Prophet's cmdstan
    # backend isn't installed (see Ch2 §2.2.1 — Windows dev machines need
    # an extra C++ toolchain step Prophet doesn't need on the Linux
    # deployment target).
    from app.core.windows_toolchain import ensure_windows_cmdstan_toolchain

    ensure_windows_cmdstan_toolchain()
    from prophet import Prophet

    today = today or date.today()
    grouped = _load_grouped_orders(db)

    # A Forecast is keyed by (menu_item_id, meal_period, forecast_date). Each
    # daily run re-predicts the dates still ahead of it, so existing rows are
    # updated in place rather than appended to — appending left duplicates
    # that staffing and procurement then double-counted. Updating (not
    # delete-and-reinsert) also keeps forecast_id stable for the prep,
    # staffing and procurement rows that reference it.
    existing_forecasts: dict[tuple[int, str, date], Forecast] = {
        (f.menu_item_id, f.meal_period, f.forecast_date): f
        for f in db.scalars(select(Forecast).where(Forecast.forecast_date > today))
    }

    created_forecasts: list[Forecast] = []
    updated_count = 0
    skipped: list[dict] = []

    for (menu_item_id, meal_period), group in grouped.groupby(["menu_item_id", "meal_period"]):
        if len(group) < MIN_DATA_POINTS:
            # Step 4-6 — UC-DF-02 Alt Flow 2a.
            skipped.append(
                {
                    "menu_item_id": int(menu_item_id),
                    "meal_period": meal_period,
                    "reason": "insufficient_data",
                    "data_points": len(group),
                }
            )
            continue

        # Steps 8-11.
        # uncertainty_samples=0: only the point forecast (yhat) is stored, so
        # skip Prophet's Monte Carlo interval sampling, which costs real time
        # per model and which nothing reads.
        model = Prophet(
            weekly_seasonality=True,
            yearly_seasonality=True,
            daily_seasonality=False,
            uncertainty_samples=0,
        )
        model.fit(group[["ds", "y"]])
        future = model.make_future_dataframe(periods=FORECAST_HORIZON_DAYS)
        forecast_df = model.predict(future)

        # Only the newly-forecasted future dates get stored — historical
        # dates are already in `group`, we don't re-store predictions for
        # days we already have real order data for.
        future_rows = forecast_df[forecast_df["ds"].dt.date > today]

        # FR4.5 — computed once per (item, meal_period) rather than per
        # row, since it's the same leftover history regardless of which
        # future date is being predicted.
        adjustment = _leftover_adjustment_factor(db, int(menu_item_id), today=today)

        # FR5.4 / UC-KO-04 — "high-demand alert...based on the latest
        # forecast": a forecast is a spike if it clears
        # HIGH_DEMAND_MULTIPLIER times this item/meal_period's own
        # historical average order volume. Computed once per group, same
        # as the adjustment factor above.
        historical_average = float(group["y"].mean())

        # Step 13.
        high_demand_threshold = historical_average * HIGH_DEMAND_MULTIPLIER
        for _, row in future_rows.iterrows():
            predicted_quantity = max(0.0, round(float(row["yhat"]) * adjustment, 2))
            forecast_date = row["ds"].date()
            key = (int(menu_item_id), meal_period, forecast_date)

            was_high_demand = False
            existing = existing_forecasts.get(key)
            if existing is None:
                forecast = Forecast(
                    menu_item_id=int(menu_item_id),
                    meal_period=meal_period,
                    forecast_date=forecast_date,
                    predicted_quantity=predicted_quantity,
                )
                db.add(forecast)
                created_forecasts.append(forecast)
                existing_forecasts[key] = forecast
            else:
                was_high_demand = (
                    historical_average > 0 and float(existing.predicted_quantity) > high_demand_threshold
                )
                existing.predicted_quantity = predicted_quantity
                existing.generated_at = datetime.now(timezone.utc)
                updated_count += 1

            # Alert only when a forecast is new or newly crosses the
            # threshold, so the daily re-run doesn't re-send the same alert
            # for a date that was already flagged.
            if historical_average > 0 and predicted_quantity > high_demand_threshold and not was_high_demand:
                notification_service.notify(
                    db,
                    recipient_role="Kitchen Staff",
                    type_="high_demand_alert",
                    message=(
                        f"High demand forecast for menu item #{int(menu_item_id)} on "
                        f"{forecast_date} ({meal_period}): {predicted_quantity} portions "
                        f"(usual average: {round(historical_average, 1)})."
                    ),
                )

    db.commit()
    for f in created_forecasts:
        db.refresh(f)

    accuracy_created = _backfill_forecast_accuracy(db, today=today)

    return {
        "forecasts_created": len(created_forecasts),
        "forecasts_updated": updated_count,
        "skipped": skipped,
        "accuracy_records_created": accuracy_created,
    }


def _backfill_forecast_accuracy(db: Session, *, today: date) -> int:
    """Steps 14-17 of Algorithm 1: for any past forecast that doesn't yet
    have an accuracy record and now has real order data on that date,
    compute the error and store it (FR4.4)."""
    past_unscored = db.execute(
        select(Forecast)
        .where(Forecast.forecast_date < today)
        .where(~Forecast.forecast_id.in_(select(ForecastAccuracy.forecast_id)))
    ).scalars().all()

    created = 0
    for forecast in past_unscored:
        actual = db.execute(
            select(Order.quantity)
            .where(Order.menu_item_id == forecast.menu_item_id)
            .where(Order.meal_period == forecast.meal_period)
            .where(Order.order_date == forecast.forecast_date)
        ).scalars().all()
        if not actual:
            continue  # no real order data for that date yet — nothing to score against

        actual_quantity = sum(actual)
        if actual_quantity == 0:
            continue  # avoid a division by zero on a genuinely zero-order day

        error = abs(actual_quantity - float(forecast.predicted_quantity)) / actual_quantity
        db.add(
            ForecastAccuracy(
                forecast_id=forecast.forecast_id,
                actual_quantity=actual_quantity,
                accuracy_error=round(error, 4),
            )
        )
        created += 1

    db.commit()
    return created


def get_latest_forecast(
    db: Session, *, menu_item_id: int, meal_period: str, forecast_date: date
) -> Forecast | None:
    """Used by Module 5 (Kitchen Operations) to derive prep recommendations
    (FR5.1) from the most recently generated forecast for a given
    item/meal-period/date, per Ch4 §4.3.1's Forecast.generated_at note:
    "surfaced to relevant roles without reprocessing on each query.\""""
    return db.execute(
        select(Forecast)
        .where(Forecast.menu_item_id == menu_item_id)
        .where(Forecast.meal_period == meal_period)
        .where(Forecast.forecast_date == forecast_date)
        .order_by(Forecast.generated_at.desc())
    ).scalars().first()


def record_order(db: Session, data) -> Order:
    """Historical order intake (FR4.1's raw input). No dedicated FR covers
    order entry itself — Order is populated by whatever front-of-house/POS
    integration is out of this system's scope (Ch1 §1.2.2: "internal use
    only... no customer-facing functionality"); this endpoint exists so the
    forecasting pipeline has real data to train against in the meantime."""
    order = Order(
        menu_item_id=data.menu_item_id,
        quantity=data.quantity,
        meal_period=data.meal_period,
        order_date=data.order_date,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def list_orders(
    db: Session, *, menu_item_id: int | None = None, limit: int = 100, offset: int = 0
) -> list[Order]:
    """The read side of record_order — historical order data was
    previously write-only, with no way to review what had been entered."""
    stmt = (
        select(Order)
        .order_by(Order.order_date.desc(), Order.order_id.desc())
        .limit(limit)
        .offset(offset)
    )
    if menu_item_id is not None:
        stmt = stmt.where(Order.menu_item_id == menu_item_id)
    return list(db.scalars(stmt))


def list_forecasts(
    db: Session,
    *,
    menu_item_id: int | None = None,
    meal_period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Forecast]:
    stmt = (
        select(Forecast)
        .order_by(Forecast.forecast_date, Forecast.forecast_id)
        .limit(limit)
        .offset(offset)
    )
    if menu_item_id is not None:
        stmt = stmt.where(Forecast.menu_item_id == menu_item_id)
    if meal_period is not None:
        stmt = stmt.where(Forecast.meal_period == meal_period)
    if date_from is not None:
        stmt = stmt.where(Forecast.forecast_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Forecast.forecast_date <= date_to)
    return list(db.scalars(stmt))


def forecast_availability(db: Session, *, menu_item_id: int | None = None, today: date | None = None) -> list[dict]:
    """FR4.6 / UC-DF-01 Alt Flow 3a — for every active menu item (and each
    meal period it has order history for), says whether a forecast exists
    and, if not, why, including the minimum data threshold. Previously an
    item without enough history just had no forecast rows and nothing told
    the user why."""
    today = today or date.today()

    items = db.execute(
        select(MenuItem.menu_item_id, MenuItem.name).where(MenuItem.is_active.is_(True)).order_by(MenuItem.name)
    ).all()
    if menu_item_id is not None:
        items = [i for i in items if i.menu_item_id == menu_item_id]

    history: dict[int, dict[str, int]] = {}
    for mid, period, days in db.execute(
        select(Order.menu_item_id, Order.meal_period, func.count(func.distinct(Order.order_date))).group_by(
            Order.menu_item_id, Order.meal_period
        )
    ):
        history.setdefault(mid, {})[period] = days

    forecasted = {
        (mid, period)
        for mid, period in db.execute(
            select(Forecast.menu_item_id, Forecast.meal_period).where(Forecast.forecast_date > today).distinct()
        )
    }

    results: list[dict] = []
    for mid, name in items:
        periods = history.get(mid)
        if not periods:
            results.append(
                {
                    "menu_item_id": mid,
                    "menu_item_name": name,
                    "meal_period": None,
                    "data_points": 0,
                    "minimum_required": MIN_DATA_POINTS,
                    "available": False,
                    "message": (
                        f"Forecasts are not yet available for {name}: it has no order history yet "
                        f"(at least {MIN_DATA_POINTS} days of orders are needed)."
                    ),
                }
            )
            continue
        for period in sorted(periods):
            days = periods[period]
            available = (mid, period) in forecasted
            if available:
                message = None
            elif days < MIN_DATA_POINTS:
                message = (
                    f"Forecasts are not yet available for {name} ({period}): {days} of the "
                    f"{MIN_DATA_POINTS} days of order history needed so far."
                )
            else:
                message = (
                    f"{name} ({period}) has enough history; its forecast will appear after the "
                    "next scheduled training run."
                )
            results.append(
                {
                    "menu_item_id": mid,
                    "menu_item_name": name,
                    "meal_period": period,
                    "data_points": days,
                    "minimum_required": MIN_DATA_POINTS,
                    "available": available,
                    "message": message,
                }
            )
    return results


def list_forecast_accuracy(
    db: Session, *, menu_item_id: int | None = None, limit: int = 100, offset: int = 0
) -> list[dict]:
    """FR4.4 — "track forecast accuracy" implies a way to see the tracked
    records; previously the only place accuracy data surfaced was inside
    the weekly PDF report, with no direct API access. Each row carries the
    forecast it scores, so a reader can see what was predicted for what."""
    stmt = (
        select(ForecastAccuracy, Forecast)
        .join(Forecast, ForecastAccuracy.forecast_id == Forecast.forecast_id)
        .order_by(ForecastAccuracy.accuracy_id)
        .limit(limit)
        .offset(offset)
    )
    if menu_item_id is not None:
        stmt = stmt.where(Forecast.menu_item_id == menu_item_id)
    return [
        {
            "accuracy_id": a.accuracy_id,
            "forecast_id": a.forecast_id,
            "actual_quantity": a.actual_quantity,
            "accuracy_error": a.accuracy_error,
            "menu_item_id": f.menu_item_id,
            "meal_period": f.meal_period,
            "forecast_date": f.forecast_date,
            "predicted_quantity": f.predicted_quantity,
        }
        for a, f in db.execute(stmt).all()
    ]
