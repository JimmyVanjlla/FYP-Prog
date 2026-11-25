"""Expected waste for the coming days: forecast portions x recent leftover rate x ingredient cost."""
from datetime import timedelta
from decimal import Decimal

from app.core.dates import restaurant_today
from app.models.forecasting import Forecast
from tests.conftest import auth_headers, register_and_login


def _h(client, email, role):
    return auth_headers(register_and_login(client, email=email, role=role))


def _setup(client, db_session):
    manager = _h(client, "manager@restaurant.com", "Restaurant Manager")
    kitchen = _h(client, "kitchen@restaurant.com", "Kitchen Staff")
    laksa = client.post("/menu-items", json={"name": "Curry Laksa", "price": "8.00", "category": "Noodles"}, headers=manager).json()
    roti = client.post("/menu-items", json={"name": "Roti Telur", "price": "4.00", "category": "Bread"}, headers=manager).json()
    paste = client.post("/inventory/ingredients", json={"name": "Curry Paste", "unit": "kg", "current_stock": "9"}, headers=manager).json()
    supplier = client.post("/procurement/suppliers", json={"name": "Fresh Farm", "contact_info": "1"}, headers=manager).json()
    client.post(
        "/procurement/suppliers/pricing",
        json={"supplier_id": supplier["supplier_id"], "ingredient_id": paste["ingredient_id"], "unit_price": "10.00"},
        headers=manager,
    )
    client.post(
        f"/menu-items/{laksa['menu_item_id']}/recipe-links",
        json={"ingredient_id": paste["ingredient_id"], "quantity_per_serving": "0.1"},
        headers=manager,
    )
    today = restaurant_today()
    for item, qty in ((laksa, "50"), (roti, "40")):
        for offset in (0, 1):
            db_session.add(
                Forecast(
                    menu_item_id=item["menu_item_id"],
                    meal_period="Lunch",
                    forecast_date=today + timedelta(days=offset),
                    predicted_quantity=Decimal(qty),
                )
            )
    db_session.commit()
    return manager, kitchen, laksa, roti, today


def _leftover(client, kitchen, item, day, prepared, leftover):
    client.post(
        "/kitchen/leftover-logs",
        json={
            "menu_item_id": item["menu_item_id"],
            "service_period_date": day.isoformat(),
            "prepared_quantity": prepared,
            "leftover_quantity": leftover,
            "leftover_level": "x",
        },
        headers=kitchen,
    )


def test_expected_waste_is_forecast_times_leftover_rate_times_cost(client, db_session):
    manager, kitchen, laksa, roti, today = _setup(client, db_session)
    _leftover(client, kitchen, laksa, today - timedelta(days=1), "100", "20")  # 20 per cent left over

    out = client.get("/waste/prediction", headers=manager).json()

    assert len(out["dishes"]) == 1  # Roti Telur has no leftover history: nothing expected
    dish = out["dishes"][0]
    assert dish["menu_item_name"] == "Curry Laksa"
    assert Decimal(dish["forecast_portions"]) == Decimal("100.0")  # 50 + 50 over the two days forecast
    assert Decimal(dish["leftover_rate"]) == Decimal("20.0")
    assert Decimal(dish["expected_leftover_portions"]) == Decimal("20.0")
    assert Decimal(dish["expected_cost"]) == Decimal("20.00")  # 20 portions x 0.1 kg x RM 10
    assert Decimal(out["total_cost"]) == Decimal("20.00")


def test_a_dish_that_left_nothing_over_is_expected_to_waste_nothing(client, db_session):
    manager, kitchen, laksa, roti, today = _setup(client, db_session)
    _leftover(client, kitchen, laksa, today - timedelta(days=1), "100", "0")
    assert client.get("/waste/prediction", headers=manager).json()["dishes"] == []


def test_the_supervisor_can_read_the_prediction_but_the_kitchen_is_not_refused_either(client, db_session):
    manager, kitchen, *_ = _setup(client, db_session)
    supervisor = _h(client, "sup@restaurant.com", "Shift Supervisor")
    assert client.get("/waste/prediction", headers=supervisor).status_code == 200
    assert client.get("/waste/prediction?days=0", headers=manager).status_code == 422
