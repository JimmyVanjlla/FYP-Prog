"""FR3.1 — stock is reduced by consumption, not just increased by deliveries."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.forecasting import Forecast
from app.services.config import get_or_create_config
from tests.conftest import auth_headers, register_and_login

TODAY = date.today()


def _setup(client, *, stock="50", per_serving="0.200"):
    """One ingredient, one dish that uses `per_serving` of it per portion."""
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    inventory = auth_headers(register_and_login(client, email="inv@restaurant.com", role="Inventory Staff"))
    ingredient = client.post(
        "/inventory/ingredients", json={"name": "Rice", "unit": "kg", "current_stock": stock}, headers=inventory
    ).json()
    item = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager
    ).json()
    client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity_per_serving": per_serving},
        headers=manager,
    )
    return manager, inventory, ingredient, item


def _mark_applied_through(db_session, day):
    config = get_or_create_config(db_session)
    config.stock_consumption_applied_through = day
    db_session.commit()


def _order(client, headers, item, qty, day, period="Lunch"):
    client.post(
        "/forecasting/orders",
        json={"menu_item_id": item["menu_item_id"], "quantity": qty, "meal_period": period, "order_date": day.isoformat()},
        headers=headers,
    )


def _stock(client, headers, ingredient):
    rows = client.get("/inventory/ingredients", headers=headers).json()
    return Decimal(next(r for r in rows if r["ingredient_id"] == ingredient["ingredient_id"])["current_stock"])


def test_first_run_starts_the_clock_without_touching_stock(client):
    manager, inventory, ingredient, item = _setup(client)
    _order(client, manager, item, 10, TODAY - timedelta(days=1))

    resp = client.post("/inventory/consumption/apply", headers=inventory)
    assert resp.status_code == 200
    assert resp.json()["initialised"] is True
    assert _stock(client, inventory, ingredient) == Decimal("50")
    assert client.get("/config", headers=inventory).json()["stock_consumption_applied_through"] == str(
        TODAY - timedelta(days=1)
    )


def test_logged_orders_are_deducted_from_stock(client, db_session):
    manager, inventory, ingredient, item = _setup(client)
    _mark_applied_through(db_session, TODAY - timedelta(days=3))
    _order(client, manager, item, 10, TODAY - timedelta(days=1))
    _order(client, manager, item, 5, TODAY - timedelta(days=2))

    body = client.post("/inventory/consumption/apply", headers=inventory).json()

    assert body["days_applied"] == 2
    assert body["ingredients_updated"] == 1
    # 15 portions x 0.2 kg
    assert _stock(client, inventory, ingredient) == Decimal("47.000")


def test_running_twice_does_not_deduct_twice(client, db_session):
    manager, inventory, ingredient, item = _setup(client)
    _mark_applied_through(db_session, TODAY - timedelta(days=2))
    _order(client, manager, item, 10, TODAY - timedelta(days=1))

    client.post("/inventory/consumption/apply", headers=inventory)
    again = client.post("/inventory/consumption/apply", headers=inventory).json()

    assert again["days_applied"] == 0
    assert _stock(client, inventory, ingredient) == Decimal("48.000")


def test_forecast_stands_in_where_no_orders_were_logged(client, db_session):
    manager, inventory, ingredient, item = _setup(client)
    _mark_applied_through(db_session, TODAY - timedelta(days=2))
    yesterday = TODAY - timedelta(days=1)

    # Lunch: forecast only -> the forecast (20) is used.
    # Dinner: forecast 20 AND a logged 10 -> the real figure (10) wins, not the sum.
    for period in ("Lunch", "Dinner"):
        db_session.add(
            Forecast(
                menu_item_id=item["menu_item_id"],
                meal_period=period,
                forecast_date=yesterday,
                predicted_quantity=Decimal("20.00"),
            )
        )
    db_session.commit()
    _order(client, manager, item, 10, yesterday, period="Dinner")

    client.post("/inventory/consumption/apply", headers=inventory)

    # (20 + 10) portions x 0.2 kg
    assert _stock(client, inventory, ingredient) == Decimal("44.000")


def test_stock_never_goes_negative(client, db_session):
    manager, inventory, ingredient, item = _setup(client, stock="1")
    _mark_applied_through(db_session, TODAY - timedelta(days=2))
    _order(client, manager, item, 100, TODAY - timedelta(days=1))

    client.post("/inventory/consumption/apply", headers=inventory)

    assert _stock(client, inventory, ingredient) == Decimal("0")


def test_inventory_staff_alerted_when_consumption_pushes_an_ingredient_below_threshold(client, db_session):
    manager, inventory, ingredient, item = _setup(client, stock="12")  # system default threshold is 10
    _mark_applied_through(db_session, TODAY - timedelta(days=2))
    _order(client, manager, item, 20, TODAY - timedelta(days=1))  # uses 4 kg -> 8 kg left

    body = client.post("/inventory/consumption/apply", headers=inventory).json()

    assert body["low_stock_alerts"] == 1
    alerts = [n for n in client.get("/kitchen/notifications", headers=inventory).json() if n["type"] == "low_stock_alert"]
    assert len(alerts) == 1
    assert "Rice" in alerts[0]["message"]


def test_kitchen_staff_cannot_trigger_consumption(client):
    token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    assert client.post("/inventory/consumption/apply", headers=auth_headers(token)).status_code == 403
