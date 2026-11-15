"""Review fixes, batch 3: restock decisions, Owner = Manager, deleting staff,
the busyness outlook, meal periods per dish, and leftover percentages."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.forecasting import Forecast, Order
from app.models.user import User
from tests.conftest import auth_headers, register_and_login


def _h(client, email, role):
    return auth_headers(register_and_login(client, email=email, role=role))


# ---------------------------------------------------------------- restock requests
def _restock_setup(client):
    inv = _h(client, "inv@restaurant.com", "Inventory Staff")
    kitchen = _h(client, "kitchen@restaurant.com", "Kitchen Staff")
    ingredient = client.post(
        "/inventory/ingredients", json={"name": "Beansprouts", "unit": "kg", "current_stock": "5"}, headers=inv
    ).json()
    request = client.post(
        "/inventory/restocking-requests",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity": "20", "urgency": True},
        headers=kitchen,
    ).json()
    return inv, kitchen, request


def test_restock_approval_is_recorded_and_the_kitchen_is_told(client):
    inv, kitchen, request = _restock_setup(client)
    resp = client.patch(
        f"/inventory/restocking-requests/{request['request_id']}", json={"status": "fulfilled"}, headers=inv
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "fulfilled" and body["decided_by"] and body["decided_at"]
    messages = [n["message"] for n in client.get("/kitchen/notifications", headers=kitchen).json()]
    assert any("Beansprouts" in m and "approved" in m for m in messages)


def test_restock_decline_needs_a_reason_in_words_and_it_reaches_the_kitchen(client):
    inv, kitchen, request = _restock_setup(client)
    url = f"/inventory/restocking-requests/{request['request_id']}"
    assert client.patch(url, json={"status": "declined"}, headers=inv).status_code == 422
    assert client.patch(url, json={"status": "declined", "note": "12345"}, headers=inv).status_code == 422
    resp = client.patch(url, json={"status": "declined", "note": "Already ordered, arrives Tuesday"}, headers=inv)
    assert resp.status_code == 200 and resp.json()["decision_note"] == "Already ordered, arrives Tuesday"
    messages = [n["message"] for n in client.get("/kitchen/notifications", headers=kitchen).json()]
    assert any("declined" in m and "arrives Tuesday" in m for m in messages)


def test_a_restock_request_is_decided_once(client):
    inv, _, request = _restock_setup(client)
    url = f"/inventory/restocking-requests/{request['request_id']}"
    assert client.patch(url, json={"status": "fulfilled"}, headers=inv).status_code == 200
    assert client.patch(url, json={"status": "declined", "note": "Changed my mind"}, headers=inv).status_code == 409


# ---------------------------------------------------------------- Owner = Manager
def test_an_owner_can_do_what_a_manager_can(client):
    owner = _h(client, "owner@restaurant.com", "Restaurant Owner")
    item = client.post("/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=owner)
    assert item.status_code == 201
    assert client.get("/config", headers=owner).status_code == 200
    ing = client.post(
        "/inventory/ingredients",
        json={"name": "Rice", "unit": "kg", "current_stock": "10"},
        headers=owner,
    )
    # Inventory writes are open to the Manager, so to the Owner as well.
    assert ing.status_code in (200, 201)


def test_a_kitchen_account_still_cannot_use_manager_routes(client):
    kitchen = _h(client, "kitchen@restaurant.com", "Kitchen Staff")
    resp = client.post("/menu-items", json={"name": "X", "price": "1.00", "category": "Y"}, headers=kitchen)
    assert resp.status_code == 403


# ---------------------------------------------------------------- deleting staff
def _two_accounts(client):
    manager = _h(client, "manager@restaurant.com", "Restaurant Manager")
    cook = client.post(
        "/users",
        json={"name": "Cook", "email": "cook@restaurant.com", "password": "Password123!", "role": "Kitchen Staff"},
        headers=manager,
    ).json()
    return manager, cook


def test_only_a_deactivated_account_can_be_deleted(client):
    manager, cook = _two_accounts(client)
    url = f"/users/{cook['user_id']}"
    assert client.delete(url, headers=manager).status_code == 409  # still active
    client.patch(url, json={"is_active": False}, headers=manager)
    assert client.delete(url, headers=manager).status_code == 200


def test_a_deleted_account_leaves_the_list_and_can_be_restored(client):
    manager, cook = _two_accounts(client)
    url = f"/users/{cook['user_id']}"
    client.patch(url, json={"is_active": False}, headers=manager)
    client.delete(url, headers=manager)

    names = [u["name"] for u in client.get("/users", headers=manager).json()]
    assert "Cook" not in names
    deleted = client.get("/users", params={"deleted": True}, headers=manager).json()
    assert [u["name"] for u in deleted] == ["Cook"] and deleted[0]["deleted_at"]

    restored = client.post(f"{url}/restore", headers=manager)
    assert restored.status_code == 200 and restored.json()["deleted_at"] is None
    assert restored.json()["is_active"] is False  # comes back deactivated
    assert "Cook" in [u["name"] for u in client.get("/users", headers=manager).json()]


def test_a_deleted_account_cannot_log_in(client):
    manager, cook = _two_accounts(client)
    url = f"/users/{cook['user_id']}"
    client.patch(url, json={"is_active": False}, headers=manager)
    client.delete(url, headers=manager)
    resp = client.post("/auth/login", json={"email": "cook@restaurant.com", "password": "Password123!"})
    assert resp.status_code in (401, 403)


def test_after_60_days_a_deleted_account_is_purged_and_cannot_come_back(client, db_session):
    manager, cook = _two_accounts(client)
    url = f"/users/{cook['user_id']}"
    client.patch(url, json={"is_active": False}, headers=manager)
    client.delete(url, headers=manager)

    row = db_session.get(User, cook["user_id"])
    row.deleted_at = datetime.now(timezone.utc) - timedelta(days=61)
    db_session.commit()

    assert client.get("/users", params={"deleted": True}, headers=manager).json() == []
    db_session.expire_all()
    purged = db_session.get(User, cook["user_id"])
    assert purged.purged_at is not None and purged.name == "Former staff member"
    assert purged.email != "cook@restaurant.com"
    assert client.post(f"{url}/restore", headers=manager).status_code == 410
    # The address is free to use again.
    again = client.post(
        "/users",
        json={"name": "New Cook", "email": "cook@restaurant.com", "password": "Password123!", "role": "Kitchen Staff"},
        headers=manager,
    )
    assert again.status_code == 201


def test_deleting_a_recent_account_keeps_it_for_the_full_60_days(client, db_session):
    manager, cook = _two_accounts(client)
    url = f"/users/{cook['user_id']}"
    client.patch(url, json={"is_active": False}, headers=manager)
    client.delete(url, headers=manager)
    row = db_session.get(User, cook["user_id"])
    row.deleted_at = datetime.now(timezone.utc) - timedelta(days=59)
    db_session.commit()
    assert len(client.get("/users", params={"deleted": True}, headers=manager).json()) == 1


def test_a_manager_cannot_delete_a_manager_but_an_owner_can(client):
    owner = _h(client, "owner@restaurant.com", "Restaurant Owner")
    manager = _h(client, "manager@restaurant.com", "Restaurant Manager")
    other = client.post(
        "/users",
        json={"name": "Other", "email": "other@restaurant.com", "password": "Password123!", "role": "Restaurant Manager"},
        headers=owner,
    ).json()
    url = f"/users/{other['user_id']}"
    client.patch(url, json={"is_active": False}, headers=owner)
    assert client.delete(url, headers=manager).status_code == 403
    assert client.delete(url, headers=owner).status_code == 200


# ---------------------------------------------------------------- staffing
def test_only_kitchen_staff_can_be_put_on_the_kitchen_station(client):
    supervisor = _h(client, "sup@restaurant.com", "Shift Supervisor")
    delivery = register_and_login(client, email="delivery@restaurant.com", role="Delivery/Logistics Staff")
    delivery_id = client.get("/users/me", headers=auth_headers(delivery)).json()["user_id"]
    schedule = client.post("/staffing/schedules", json={"date": "2026-09-01", "meal_period": "Lunch"}, headers=supervisor).json()
    resp = client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/assignments",
        json={"staff_id": delivery_id, "station": "Kitchen"},
        headers=supervisor,
    )
    assert resp.status_code == 422 and "Kitchen Staff" in resp.json()["detail"]


# ---------------------------------------------------------------- busyness outlook
def test_outlook_says_how_busy_each_day_is_against_a_typical_day(client, db_session):
    manager = _h(client, "manager@restaurant.com", "Restaurant Manager")
    item = client.post("/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager).json()
    today = date.today()
    # A typical Lunch is 100 portions.
    for i in range(1, 15):
        db_session.add(Order(menu_item_id=item["menu_item_id"], quantity=100, meal_period="Lunch", order_date=today - timedelta(days=i)))
    for offset, predicted in ((1, 140), (2, 100), (3, 60)):
        db_session.add(
            Forecast(menu_item_id=item["menu_item_id"], meal_period="Lunch", forecast_date=today + timedelta(days=offset), predicted_quantity=Decimal(predicted))
        )
    db_session.commit()

    rows = client.get(
        "/forecasting/outlook",
        params={"date_from": (today + timedelta(days=1)).isoformat(), "date_to": (today + timedelta(days=3)).isoformat()},
        headers=manager,
    ).json()
    by_level = {r["level"]: r for r in rows}
    assert set(by_level) == {"Busy", "Normal", "Quiet"}
    assert by_level["Busy"]["predicted_portions"] == 140 and by_level["Busy"]["typical_portions"] == 100
    assert by_level["Busy"]["recommended_kitchen_staff"] == 5  # ceil(140 / 30)
    assert by_level["Quiet"]["recommended_kitchen_staff"] == 4  # never fewer than 4


# ---------------------------------------------------------------- meal periods per dish
def test_a_dish_is_served_at_lunch_and_dinner_unless_set_otherwise(client):
    manager = _h(client, "manager@restaurant.com", "Restaurant Manager")
    item = client.post("/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager).json()
    assert item["meal_periods"] == ["Lunch", "Dinner"]
    breakfast = client.post(
        "/menu-items",
        json={"name": "Roti Canai", "price": "2.20", "category": "Bread", "meal_periods": ["Breakfast", "Lunch"]},
        headers=manager,
    ).json()
    assert breakfast["meal_periods"] == ["Breakfast", "Lunch"]
    updated = client.put(
        f"/menu-items/{breakfast['menu_item_id']}", json={"meal_periods": ["Dinner", "Breakfast"]}, headers=manager
    ).json()
    assert updated["meal_periods"] == ["Breakfast", "Dinner"]  # kept in day order
    assert client.put(f"/menu-items/{breakfast['menu_item_id']}", json={"meal_periods": []}, headers=manager).status_code == 422
    assert client.put(f"/menu-items/{breakfast['menu_item_id']}", json={"meal_periods": ["Brunch"]}, headers=manager).status_code == 422


def test_there_is_no_prep_for_a_meal_period_the_dish_is_not_served_in(client):
    manager = _h(client, "manager@restaurant.com", "Restaurant Manager")
    kitchen = _h(client, "kitchen@restaurant.com", "Kitchen Staff")
    item = client.post(
        "/menu-items",
        json={"name": "Teh Tarik", "price": "3.00", "category": "Drink", "meal_periods": ["Lunch"]},
        headers=manager,
    ).json()
    resp = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Dinner", "forecast_date": "2026-11-20", "manual_quantity": 10},
        headers=kitchen,
    )
    assert resp.status_code == 422 and "not served at Dinner" in resp.json()["detail"]
    ok = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Lunch", "forecast_date": "2026-11-20", "manual_quantity": 10},
        headers=kitchen,
    )
    assert ok.status_code in (200, 201)


# ---------------------------------------------------------------- leftover percentages
def _dish_with_confirmed_prep(client, quantity="40"):
    manager = _h(client, "manager@restaurant.com", "Restaurant Manager")
    inv = _h(client, "inv@restaurant.com", "Inventory Staff")
    kitchen = _h(client, "kitchen@restaurant.com", "Kitchen Staff")
    item = client.post("/menu-items", json={"name": "Curry Laksa", "price": "8.00", "category": "Noodles"}, headers=manager).json()
    ingredient = client.post(
        "/inventory/ingredients", json={"name": "Coconut Milk", "unit": "litre", "current_stock": "50"}, headers=inv
    ).json()
    client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity_per_serving": "0.1"},
        headers=manager,
    )
    rec = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Lunch", "forecast_date": "2026-10-01", "manual_quantity": quantity},
        headers=kitchen,
    ).json()
    client.post(
        f"/kitchen/prep-recommendations/{rec['recommendation_id']}/confirm",
        json={"confirmed_quantity": quantity},
        headers=kitchen,
    )
    return manager, kitchen, item


def test_a_leftover_percentage_is_worked_out_from_the_confirmed_prep(client):
    manager, kitchen, item = _dish_with_confirmed_prep(client, "40")
    resp = client.post(
        "/kitchen/leftover-logs",
        json={"menu_item_id": item["menu_item_id"], "service_period_date": "2026-10-01", "meal_period": "Lunch", "leftover_percent": 25},
        headers=kitchen,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert (body["prepared_quantity"], body["leftover_quantity"]) == ("40.00", "10.00")
    assert body["leftover_percent"] == 25 and body["leftover_level"] == "25% left over"
    # The waste cost still flows: 10 servings x 0.1 litre.
    logs = client.get("/waste/logs", headers=manager).json()
    assert logs[0]["quantity_wasted"] == "1.000"


def test_a_leftover_percentage_needs_a_prep_quantity_to_take_a_percentage_of(client):
    manager, kitchen, item = _dish_with_confirmed_prep(client)
    resp = client.post(
        "/kitchen/leftover-logs",
        json={"menu_item_id": item["menu_item_id"], "service_period_date": "2026-10-02", "meal_period": "Lunch", "leftover_percent": 50},
        headers=kitchen,
    )
    assert resp.status_code == 422 and "Confirm the prep first" in resp.json()["detail"]


@pytest.mark.parametrize("percent", [10, 30, 101, -5])
def test_only_the_standard_percentages_are_accepted(client, percent):
    manager, kitchen, item = _dish_with_confirmed_prep(client)
    resp = client.post(
        "/kitchen/leftover-logs",
        json={"menu_item_id": item["menu_item_id"], "service_period_date": "2026-10-01", "meal_period": "Lunch", "leftover_percent": percent},
        headers=kitchen,
    )
    assert resp.status_code == 422


def test_a_percentage_needs_a_meal_period_and_the_old_quantities_still_work(client):
    manager, kitchen, item = _dish_with_confirmed_prep(client)
    no_period = client.post(
        "/kitchen/leftover-logs",
        json={"menu_item_id": item["menu_item_id"], "service_period_date": "2026-10-01", "leftover_percent": 25},
        headers=kitchen,
    )
    assert no_period.status_code == 422
    legacy = client.post(
        "/kitchen/leftover-logs",
        json={"menu_item_id": item["menu_item_id"], "service_period_date": "2026-10-03", "prepared_quantity": "30", "leftover_quantity": "3", "leftover_level": "Partially Eaten"},
        headers=kitchen,
    )
    assert legacy.status_code == 201 and legacy.json()["leftover_percent"] is None
