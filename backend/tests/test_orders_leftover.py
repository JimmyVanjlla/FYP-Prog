"""Incoming orders the kitchen works through, and leftover worked out from them:
leftover = confirmed prep - portions served (completed orders)."""
from datetime import date, timedelta

from app.models.forecasting import Order
from tests.conftest import auth_headers, register_and_login

DAY = date(2026, 10, 1)


def _h(client, email, role):
    return auth_headers(register_and_login(client, email=email, role=role))


def _setup(client, prep="8"):
    manager = _h(client, "manager@restaurant.com", "Restaurant Manager")
    supervisor = _h(client, "sup@restaurant.com", "Shift Supervisor")
    kitchen = _h(client, "kitchen@restaurant.com", "Kitchen Staff")
    laksa = client.post("/menu-items", json={"name": "Curry Laksa", "price": "8.00", "category": "Noodles"}, headers=manager).json()
    roti = client.post("/menu-items", json={"name": "Roti Telur", "price": "4.00", "category": "Bread"}, headers=manager).json()
    milk = client.post(
        "/inventory/ingredients", json={"name": "Coconut Milk", "unit": "litre", "current_stock": "50"}, headers=supervisor
    ).json()
    client.post(
        f"/menu-items/{laksa['menu_item_id']}/recipe-links",
        json={"ingredient_id": milk["ingredient_id"], "quantity_per_serving": "0.1"},
        headers=manager,
    )
    rec = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": laksa["menu_item_id"], "meal_period": "Lunch", "forecast_date": DAY.isoformat(), "manual_quantity": prep},
        headers=kitchen,
    ).json()
    client.post(
        f"/kitchen/prep-recommendations/{rec['recommendation_id']}/confirm", json={"confirmed_quantity": prep}, headers=kitchen
    )
    return manager, supervisor, kitchen, laksa, roti


def _order(db_session, item, quantity, status="completed", day=DAY, period="Lunch"):
    order = Order(menu_item_id=item["menu_item_id"], quantity=quantity, meal_period=period, order_date=day, status=status)
    db_session.add(order)
    db_session.commit()
    return order


# ---------------------------------------------------------------- order status
def test_an_order_moves_from_pending_to_preparing_to_completed_and_never_back(client, db_session):
    manager, supervisor, kitchen, laksa, _ = _setup(client)
    order = _order(db_session, laksa, 2, status="pending")
    url = f"/orders/{order.order_id}/status"

    assert client.patch(url, json={"status": "preparing"}, headers=kitchen).json()["status"] == "preparing"
    assert client.patch(url, json={"status": "preparing"}, headers=kitchen).status_code == 409
    assert client.patch(url, json={"status": "completed"}, headers=kitchen).json()["status"] == "completed"
    assert client.patch(url, json={"status": "preparing"}, headers=kitchen).status_code == 409
    assert client.patch(url, json={"status": "pending"}, headers=kitchen).status_code == 422


def test_the_supervisor_can_see_orders_but_not_change_them(client, db_session):
    manager, supervisor, kitchen, laksa, _ = _setup(client)
    order = _order(db_session, laksa, 1, status="pending")
    assert client.get(f"/orders?order_date={DAY}&meal_period=Lunch", headers=supervisor).status_code == 200
    resp = client.patch(f"/orders/{order.order_id}/status", json={"status": "preparing"}, headers=supervisor)
    assert resp.status_code == 403


def test_orders_are_listed_with_dish_names_for_a_day_and_meal_period(client, db_session):
    manager, supervisor, kitchen, laksa, roti = _setup(client)
    _order(db_session, laksa, 2, status="pending")
    _order(db_session, roti, 1, status="preparing")
    _order(db_session, roti, 1, day=DAY + timedelta(days=1))
    rows = client.get(f"/orders?order_date={DAY}&meal_period=Lunch", headers=kitchen).json()
    assert sorted((r["menu_item_name"], r["quantity"], r["status"]) for r in rows) == [
        ("Curry Laksa", 2, "pending"),
        ("Roti Telur", 1, "preparing"),
    ]
    only_pending = client.get(f"/orders?order_date={DAY}&status=pending", headers=kitchen).json()
    assert len(only_pending) == 1


def test_complete_all_finishes_everything_still_open(client, db_session):
    manager, supervisor, kitchen, laksa, _ = _setup(client)
    _order(db_session, laksa, 1, status="pending")
    _order(db_session, laksa, 2, status="preparing")
    _order(db_session, laksa, 3, status="completed")
    resp = client.post("/orders/complete-all", json={"order_date": DAY.isoformat(), "meal_period": "Lunch"}, headers=kitchen)
    assert resp.json() == {"count": 2}
    rows = client.get(f"/orders?order_date={DAY}", headers=kitchen).json()
    assert {r["status"] for r in rows} == {"completed"}


def test_simulated_orders_cover_the_dishes_served_and_are_not_doubled(client):
    manager, supervisor, kitchen, laksa, roti = _setup(client, prep="20")
    lunch_only = client.post(
        "/menu-items",
        json={"name": "Teh Tarik", "price": "3.00", "category": "Drink", "meal_periods": ["Lunch"]},
        headers=manager,
    ).json()
    tea = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": lunch_only["menu_item_id"], "meal_period": "Lunch", "forecast_date": DAY.isoformat(), "manual_quantity": 10},
        headers=kitchen,
    ).json()
    client.post(
        f"/kitchen/prep-recommendations/{tea['recommendation_id']}/confirm", json={"confirmed_quantity": 10}, headers=kitchen
    )
    body = {"order_date": DAY.isoformat(), "meal_period": "Dinner"}
    dinner = client.post("/orders/simulate", json=body, headers=kitchen)
    assert dinner.status_code == 201 and dinner.json() == []  # no forecast and no prep for dinner: nothing to base orders on

    first = client.post("/orders/simulate", json={**body, "meal_period": "Lunch"}, headers=kitchen).json()
    assert first and {o["status"] for o in first} == {"pending"}
    names = {o["menu_item_name"] for o in first}
    assert names == {"Curry Laksa", "Teh Tarik"}  # Roti Telur has no prep or forecast
    laksa_total = sum(o["quantity"] for o in first if o["menu_item_name"] == "Curry Laksa")
    assert 12 <= laksa_total <= 20  # 60 to 100 per cent of the 20 confirmed
    again = client.post("/orders/simulate", json={**body, "meal_period": "Lunch"}, headers=kitchen).json()
    assert again == []


# ---------------------------------------------------------------- leftover from sales
def test_leftover_is_confirmed_prep_minus_portions_served(client, db_session):
    """8 portions prepared, 5 served: 3 are left (38 per cent)."""
    manager, supervisor, kitchen, laksa, roti = _setup(client, prep="8")
    _order(db_session, laksa, 2)
    _order(db_session, laksa, 3)
    _order(db_session, laksa, 4, status="pending")  # not served yet: does not count
    summary = client.get(f"/kitchen/leftover-summary?service_date={DAY}&meal_period=Lunch", headers=kitchen).json()
    dish = next(d for d in summary["dishes"] if d["menu_item_name"] == "Curry Laksa")
    assert (dish["prepared"], dish["served"], dish["leftover"], dish["leftover_percent"]) == ("8.00", 5, "3.00", 38)
    assert summary["open_orders"] == 1
    other = next(d for d in summary["dishes"] if d["menu_item_name"] == "Roti Telur")
    assert other["prep_confirmed"] is False and other["leftover"] is None  # nothing was confirmed to measure against


def test_selling_more_than_was_prepared_leaves_nothing_and_says_so(client, db_session):
    manager, supervisor, kitchen, laksa, _ = _setup(client, prep="8")
    _order(db_session, laksa, 10)
    dish = client.get(f"/kitchen/leftover-summary?service_date={DAY}&meal_period=Lunch", headers=kitchen).json()["dishes"][0]
    assert (dish["leftover"], dish["leftover_percent"], dish["sold_beyond_prep"]) == ("0.00", 0, 2)


def test_recording_saves_the_leftover_and_costs_the_waste_once(client, db_session):
    manager, supervisor, kitchen, laksa, _ = _setup(client, prep="8")
    _order(db_session, laksa, 5)
    body = {"service_date": DAY.isoformat(), "meal_period": "Lunch"}

    logs = client.post("/kitchen/leftovers/record", json=body, headers=kitchen)
    assert logs.status_code == 201
    log = logs.json()[0]
    assert (log["prepared_quantity"], log["leftover_quantity"], log["leftover_percent"]) == ("8.00", "3.00", 38)
    waste = client.get("/waste/logs", headers=manager).json()
    assert [w["quantity_wasted"] for w in waste] == ["0.300"]  # 3 portions x 0.1 litre

    # More orders are completed, and it is recorded again: updated, not duplicated.
    _order(db_session, laksa, 2)
    again = client.post("/kitchen/leftovers/record", json=body, headers=kitchen).json()
    assert len(again) == 1 and again[0]["log_id"] == log["log_id"] and again[0]["leftover_quantity"] == "1.00"
    waste = client.get("/waste/logs", headers=manager).json()
    assert [w["quantity_wasted"] for w in waste] == ["0.100"]
    assert len(client.get("/kitchen/leftover-logs", headers=kitchen).json()) == 1


def test_a_sold_out_dish_records_no_waste(client, db_session):
    manager, supervisor, kitchen, laksa, _ = _setup(client, prep="8")
    _order(db_session, laksa, 8)
    client.post("/kitchen/leftovers/record", json={"service_date": DAY.isoformat(), "meal_period": "Lunch"}, headers=kitchen)
    assert client.get("/waste/logs", headers=manager).json() == []


def test_only_kitchen_staff_record_leftovers(client, db_session):
    manager, supervisor, kitchen, laksa, _ = _setup(client)
    body = {"service_date": DAY.isoformat(), "meal_period": "Lunch"}
    assert client.post("/kitchen/leftovers/record", json=body, headers=supervisor).status_code == 403
    assert client.post("/kitchen/leftovers/record", json=body, headers=manager).status_code == 403


# ---------------------------------------------------------------- training
def test_forecast_training_ignores_orders_that_are_not_finished_days(client, db_session):
    from app.services.forecasting import _load_grouped_orders

    manager, supervisor, kitchen, laksa, _ = _setup(client)
    today = date(2026, 10, 10)
    _order(db_session, laksa, 7, day=today - timedelta(days=1))  # a finished day, completed
    _order(db_session, laksa, 9, day=today)  # today: still coming in
    _order(db_session, laksa, 5, status="pending", day=today - timedelta(days=2))  # never completed
    grouped = _load_grouped_orders(db_session, today)
    assert grouped["y"].tolist() == [7]
