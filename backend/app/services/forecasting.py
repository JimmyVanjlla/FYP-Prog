"""
Module 4: Demand Forecasting business logic.

Implements Algorithm 1 (Ch4 §4.8.1, "TrainAndGenerateForecast" —
UC-DF-02 / FR4.1-FR4.4) as close to the pseudocode as SQLAlchemy + pandas +
Prophet allow. Forecasts are trained per (menu_item_id, meal_period) pair —
Ch4's pseudocode says "FOR EACH menu_item", but the Forecast entity itself
is keyed by (menu_item_id, meal_period, forecast_date) and FR4.1 explicitly
says orders are "aggregated by menu item, meal period, and date", so a
separate model is trained per item/meal-period combination (breakfast,
lunch, and dinner demand for the same dish don't follow the same curve).
"""
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecasting import Forecast, ForecastAccuracy, Order

# UC-DF-02 Alt Flow 2a — below this many historical (date, meal_period)
# data points for an item, Prophet is skipped and the item is flagged
# rather than forced through a fit that would overfit noise.
MIN_DATA_POINTS = 14
# How many days ahead each training run forecasts.
FORECAST_HORIZON_DAYS = 7


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

    created_forecasts: list[Forecast] = []
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
        model = Prophet(weekly_seasonality=True, yearly_seasonality=True, daily_seasonality=False)
        model.fit(group[["ds", "y"]])
        future = model.make_future_dataframe(periods=FORECAST_HORIZON_DAYS)
        forecast_df = model.predict(future)

        # Only the newly-forecasted future dates get stored — historical
        # dates are already in `group`, we don't re-store predictions for
        # days we already have real order data for.
        future_rows = forecast_df[forecast_df["ds"].dt.date > today]

        # Step 13.
        for _, row in future_rows.iterrows():
            forecast = Forecast(
                menu_item_id=int(menu_item_id),
                meal_period=meal_period,
                forecast_date=row["ds"].date(),
                predicted_quantity=max(0.0, round(float(row["yhat"]), 2)),
            )
            db.add(forecast)
            created_forecasts.append(forecast)

    db.commit()
    for f in created_forecasts:
        db.refresh(f)

    accuracy_created = _backfill_forecast_accuracy(db, today=today)

    return {
        "forecasts_created": len(created_forecasts),
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


def list_forecasts(
    db: Session, *, menu_item_id: int | None = None, meal_period: str | None = None
) -> list[Forecast]:
    stmt = select(Forecast).order_by(Forecast.forecast_date)
    if menu_item_id is not None:
        stmt = stmt.where(Forecast.menu_item_id == menu_item_id)
    if meal_period is not None:
        stmt = stmt.where(Forecast.meal_period == meal_period)
    return list(db.scalars(stmt))
