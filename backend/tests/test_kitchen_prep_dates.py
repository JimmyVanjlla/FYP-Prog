"""The prep screen's API: a recommendation has a date, is found again rather
than duplicated, tracks the current forecast until confirmed, and can only be
confirmed once."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.forecasting import Forecast
from tests.conftest import auth_headers, register_and_login

TOMORROW = date.today() + timedelta(days=1)


def _setup(client, db_session, *, forecast_qty="40.00"):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    kitchen = auth_headers(register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff"))
    item = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager
    ).json()
    forecast = None
    if forecast_qty is not None:
        forecast = Forecast(
            menu_item_id=item["menu_item_id"],
            meal_period="Lunch",
            forecast_date=TOMORROW,
            predicted_quantity=Decimal(forecast_qty),
        )
        db_session.add(forecast)
        db_session.commit()
    return kitchen, item, forecast


def _generate(client, headers, item, **extra):
    return client.post(
        "/kitchen/prep-recommendations",
        json={
            "menu_item_id": item["menu_item_id"],
            "meal_period": "Lunch",
            "forecast_date": TOMORROW.isoformat(),
            **extra,
        },
        headers=headers,
    )


def test_recommendation_carries_its_date_and_can_be_listed_by_date(client, db_session):
    kitchen, item, _ = _setup(client, db_session)

    body = _generate(client, kitchen, item).json()
    assert body["forecast_date"] == TOMORROW.isoformat()
    assert body["confirmed"] is False

    listed = client.get(
        "/kitchen/prep-recommendations", params={"forecast_date": TOMORROW.isoformat()}, headers=kitchen
    ).json()
    assert [r["recommendation_id"] for r in listed] == [body["recommendation_id"]]
    other_day = client.get(
        "/kitchen/prep-recommendations",
        params={"forecast_date": (TOMORROW + timedelta(days=3)).isoformat()},
        headers=kitchen,
    ).json()
    assert other_day == []


def test_unconfirmed_recommendation_follows_the_forecast_as_it_is_updated(client, db_session):
    """Forecasts are updated in place each day, so a recommendation nobody
    has confirmed yet must not be left showing yesterday's number."""
    kitchen, item, forecast = _setup(client, db_session, forecast_qty="40.00")
    first = _generate(client, kitchen, item).json()
    assert Decimal(first["recommended_quantity"]) == Decimal("40.00")

    forecast.predicted_quantity = Decimal("55.00")
    db_session.commit()
    second = _generate(client, kitchen, item).json()

    assert second["recommendation_id"] == first["recommendation_id"]
    assert Decimal(second["recommended_quantity"]) == Decimal("55.00")


def test_confirmed_recommendation_is_a_record_and_does_not_change(client, db_session):
    kitchen, item, forecast = _setup(client, db_session, forecast_qty="40.00")
    rec = _generate(client, kitchen, item).json()
    client.post(
        f"/kitchen/prep-recommendations/{rec['recommendation_id']}/confirm",
        json={"confirmed_quantity": "40.00"},
        headers=kitchen,
    )

    forecast.predicted_quantity = Decimal("90.00")
    db_session.commit()
    again = _generate(client, kitchen, item).json()

    assert Decimal(again["recommended_quantity"]) == Decimal("40.00")
    assert again["confirmed"] is True
    assert Decimal(again["confirmed_quantity"]) == Decimal("40.00")


def test_manual_recommendation_is_not_duplicated_and_can_be_corrected(client, db_session):
    """UC-KO-01 Alt Flow 3a: entering a manual figure twice for the same
    item/period/day used to create two recommendations."""
    kitchen, item, _ = _setup(client, db_session, forecast_qty=None)

    first = _generate(client, kitchen, item, manual_quantity="25").json()
    second = _generate(client, kitchen, item, manual_quantity="30").json()

    assert second["recommendation_id"] == first["recommendation_id"]
    assert Decimal(second["recommended_quantity"]) == Decimal("30")
    assert len(client.get("/kitchen/prep-recommendations", headers=kitchen).json()) == 1


def test_confirming_twice_is_a_conflict_not_a_server_error(client, db_session):
    kitchen, item, _ = _setup(client, db_session)
    rec = _generate(client, kitchen, item).json()
    url = f"/kitchen/prep-recommendations/{rec['recommendation_id']}/confirm"

    assert client.post(url, json={"confirmed_quantity": "40.00"}, headers=kitchen).status_code == 201
    assert client.post(url, json={"confirmed_quantity": "40.00"}, headers=kitchen).status_code == 409
