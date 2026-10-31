"""Regression test for the yearly-seasonality finding (FORECAST_EVALUATION.md).

Prophet was configured with yearly_seasonality=True, which asks it to learn a
yearly cycle from weeks of data. On a restaurant with a few weeks of history it
then produced forecasts that drifted further from reality each day ahead (about
20% error one day out, over 100% a week out), worse than "same as last week".
Prophet's own 'auto' setting leaves the yearly term off until there are two
years of history.
"""
import random
from datetime import date, timedelta

from tests.conftest import auth_headers, register_and_login

WEEKDAY_DEMAND = 20
WEEKEND_DEMAND = 26  # +30%, as in a typical restaurant week
HISTORY_DAYS = 35


def _expected(day: date) -> int:
    return WEEKEND_DEMAND if day.weekday() >= 5 else WEEKDAY_DEMAND


def test_forecasts_with_weeks_of_history_stay_close_to_the_weekly_pattern(client):
    token = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    headers = auth_headers(token)
    item = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Main"}, headers=headers
    ).json()

    rng = random.Random(7)  # fixed seed: the same noisy history every run
    start = date.today() - timedelta(days=HISTORY_DAYS)
    for i in range(HISTORY_DAYS):
        day = start + timedelta(days=i)
        quantity = max(1, round(rng.gauss(_expected(day), _expected(day) * 0.15)))
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": quantity,
                "meal_period": "Lunch",
                "order_date": day.isoformat(),
            },
            headers=headers,
        )

    assert client.post("/forecasting/train", headers=headers).status_code == 200
    forecasts = client.get(
        "/forecasting/forecasts", params={"menu_item_id": item["menu_item_id"]}, headers=headers
    ).json()
    # History ends yesterday and only dates after today are stored: 6 days.
    assert len(forecasts) == 6

    errors = [
        abs(float(f["predicted_quantity"]) - _expected(date.fromisoformat(f["forecast_date"])))
        / _expected(date.fromisoformat(f["forecast_date"]))
        for f in forecasts
    ]
    # Noise alone costs about 12%; a model that has learned the week should be
    # near that. With the old setting this history gave about 66% on average and
    # 160% on the worst day (how bad it is varies with the weekday the test
    # runs on, so the next test pins the setting itself).
    assert sum(errors) / len(errors) < 0.25, f"mean error {sum(errors) / len(errors):.0%}: {errors}"
    assert max(errors) < 0.5, f"worst day off by {max(errors):.0%}"


def test_yearly_seasonality_is_left_to_prophets_auto_rule(client, monkeypatch):
    """Deterministic guard for the same finding: the setting must be 'auto'
    (yearly term only with two or more years of history), never forced on."""
    import prophet

    seen: list[dict] = []

    class RecordingProphet(prophet.Prophet):
        def __init__(self, *args, **kwargs):
            seen.append(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(prophet, "Prophet", RecordingProphet)

    token = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    headers = auth_headers(token)
    item = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Main"}, headers=headers
    ).json()
    start = date.today() - timedelta(days=20)
    for i in range(20):
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": 10 + i % 7,
                "meal_period": "Lunch",
                "order_date": (start + timedelta(days=i)).isoformat(),
            },
            headers=headers,
        )
    client.post("/forecasting/train", headers=headers)

    assert seen, "training did not construct a Prophet model"
    assert all(kwargs.get("yearly_seasonality") == "auto" for kwargs in seen), seen
