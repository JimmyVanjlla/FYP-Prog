"""FR4.4: an accuracy record says what it scored: which dish, period and
date, and what had been predicted, not just a forecast_id to look up."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.forecasting import Forecast, ForecastAccuracy
from tests.conftest import auth_headers, register_and_login


def test_accuracy_rows_include_the_forecast_they_score(client, db_session):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    item = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager
    ).json()
    day = date.today() - timedelta(days=2)
    forecast = Forecast(
        menu_item_id=item["menu_item_id"], meal_period="Lunch", forecast_date=day, predicted_quantity=Decimal("40.00")
    )
    db_session.add(forecast)
    db_session.flush()
    db_session.add(
        ForecastAccuracy(forecast_id=forecast.forecast_id, actual_quantity=Decimal("36.00"), accuracy_error=Decimal("0.1000"))
    )
    db_session.commit()

    rows = client.get("/forecasting/accuracy", headers=manager).json()

    assert len(rows) == 1
    assert rows[0]["menu_item_id"] == item["menu_item_id"]
    assert rows[0]["meal_period"] == "Lunch"
    assert rows[0]["forecast_date"] == day.isoformat()
    assert rows[0]["predicted_quantity"] == "40.00"
    assert rows[0]["actual_quantity"] == "36.00"


def test_accuracy_can_still_be_filtered_by_menu_item(client, db_session):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    items = [
        client.post("/menu-items", json={"name": name, "price": "5.00", "category": "Main"}, headers=manager).json()
        for name in ("Nasi Lemak", "Mee Goreng")
    ]
    day = date.today() - timedelta(days=2)
    for item in items:
        f = Forecast(
            menu_item_id=item["menu_item_id"], meal_period="Lunch", forecast_date=day, predicted_quantity=Decimal("10.00")
        )
        db_session.add(f)
        db_session.flush()
        db_session.add(ForecastAccuracy(forecast_id=f.forecast_id, actual_quantity=Decimal("9.00"), accuracy_error=Decimal("0.1000")))
    db_session.commit()

    rows = client.get(
        "/forecasting/accuracy", params={"menu_item_id": items[0]["menu_item_id"]}, headers=manager
    ).json()

    assert [r["menu_item_id"] for r in rows] == [items[0]["menu_item_id"]]
