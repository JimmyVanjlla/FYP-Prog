"""FR9.2: purchase recommendations come from forecasts, and generating them is
repeatable. They used to stack: every tap of Generate appended another full
set, so the list showed each ingredient once per tap."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.forecasting import Forecast
from tests.conftest import auth_headers, register_and_login


def _setup(client, db_session, *, stock="0"):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    officer = auth_headers(register_and_login(client, email="po@restaurant.com", role="Procurement Officer"))
    inventory = auth_headers(register_and_login(client, email="inv@restaurant.com", role="Inventory Staff"))

    item = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager
    ).json()
    ingredient = client.post(
        "/inventory/ingredients", json={"name": "Rice", "unit": "kg", "current_stock": stock}, headers=inventory
    ).json()
    client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity_per_serving": "0.2"},
        headers=manager,
    ).raise_for_status()

    db_session.add(
        Forecast(
            menu_item_id=item["menu_item_id"],
            meal_period="Lunch",
            forecast_date=date.today() + timedelta(days=1),
            predicted_quantity=Decimal("50.00"),
        )
    )
    db_session.commit()
    return officer, inventory, ingredient


def test_generating_twice_replaces_the_recommendations_instead_of_doubling_them(client, db_session):
    officer, _inventory, _ingredient = _setup(client, db_session)

    first = client.post("/procurement/recommendations/generate", headers=officer)
    second = client.post("/procurement/recommendations/generate", headers=officer)

    assert first.status_code == second.status_code == 200
    assert len(first.json()) == len(second.json()) == 1
    stored = client.get("/procurement/recommendations", headers=officer).json()
    assert len(stored) == 1
    assert Decimal(stored[0]["recommended_quantity"]) == Decimal("10.000")  # 50 portions x 0.2 kg, none in stock


def test_regenerating_reflects_current_stock_not_the_previous_run(client, db_session):
    officer, inventory, ingredient = _setup(client, db_session, stock="0")
    client.post("/procurement/recommendations/generate", headers=officer)

    # 4 kg arrives, so the shortfall against the 10 kg needed is 6 kg.
    client.post(
        "/inventory/stock-adjustments",
        json={"ingredient_id": ingredient["ingredient_id"], "adjusted_quantity": "4", "reason_category": "Correction"},
        headers=inventory,
    ).raise_for_status()
    client.post("/procurement/recommendations/generate", headers=officer)

    stored = client.get("/procurement/recommendations", headers=officer).json()
    assert len(stored) == 1
    assert Decimal(stored[0]["recommended_quantity"]) == Decimal("6.000")


def test_nothing_is_recommended_when_stock_covers_the_forecast(client, db_session):
    officer, _inventory, _ingredient = _setup(client, db_session, stock="25")
    client.post("/procurement/recommendations/generate", headers=officer)
    assert client.post("/procurement/recommendations/generate", headers=officer).json() == []
    assert client.get("/procurement/recommendations", headers=officer).json() == []
