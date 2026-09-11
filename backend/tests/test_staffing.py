from datetime import date
from decimal import Decimal

from app.models.forecasting import Forecast
from tests.conftest import auth_headers, register_and_login


def _supervisor_token(client):
    return register_and_login(client, email="supervisor@restaurant.com", role="Shift Supervisor")


def test_create_and_publish_schedule(client):
    """FR8.2."""
    token = _supervisor_token(client)
    resp = client.post(
        "/staffing/schedules", json={"date": "2026-08-22", "meal_period": "Dinner"}, headers=auth_headers(token)
    )
    assert resp.status_code == 201
    schedule = resp.json()
    assert schedule["status"] == "draft"

    publish = client.post(f"/staffing/schedules/{schedule['schedule_id']}/publish", headers=auth_headers(token))
    assert publish.json()["status"] == "published"


def test_staffing_recommendation_falls_back_with_no_forecast(client):
    """FR8.1 / UC-SS-01 Alt Flow 3a — no forecast for the date -> falls
    back gracefully (0 staff recommended, not an error) rather than
    crashing."""
    token = _supervisor_token(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-09-01", "meal_period": "Lunch"}, headers=auth_headers(token)
    ).json()

    resp = client.post(f"/staffing/schedules/{schedule['schedule_id']}/recommendations", headers=auth_headers(token))
    assert resp.status_code == 200
    recos = resp.json()
    assert len(recos) == 2  # Kitchen + Front of House
    assert all(r["recommended_staff_count"] == 0 for r in recos)


def test_staffing_recommendation_uses_forecast(client, db_session):
    """FR8.1 — portions-per-staff conversion (default ratio 30)."""
    token = _supervisor_token(client)
    manager_token = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(manager_token),
    ).json()

    forecast = Forecast(
        menu_item_id=item["menu_item_id"],
        meal_period="Lunch",
        forecast_date=date(2026, 9, 2),
        predicted_quantity=Decimal("120.00"),
    )
    db_session.add(forecast)
    db_session.commit()

    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-09-02", "meal_period": "Lunch"}, headers=auth_headers(token)
    ).json()
    resp = client.post(f"/staffing/schedules/{schedule['schedule_id']}/recommendations", headers=auth_headers(token))
    recos = resp.json()
    # 120 total portions / 2 stations = 60 each; ceil(60/30) = 2 staff each.
    assert all(r["recommended_staff_count"] == 2 for r in recos)


def test_prevent_double_assignment_to_same_shift(client):
    """FR8.5."""
    token = _supervisor_token(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-08-22", "meal_period": "Dinner"}, headers=auth_headers(token)
    ).json()
    kitchen_token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    kitchen_user_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]

    first = client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/assignments",
        json={"staff_id": kitchen_user_id, "station": "Kitchen"},
        headers=auth_headers(token),
    )
    assert first.status_code == 201

    second = client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/assignments",
        json={"staff_id": kitchen_user_id, "station": "Front of House"},
        headers=auth_headers(token),
    )
    assert second.status_code == 409


def test_shift_open_and_close_flow(client):
    """FR8.3 / FR8.4."""
    token = _supervisor_token(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-08-22", "meal_period": "Dinner"}, headers=auth_headers(token)
    ).json()
    kitchen_token = register_and_login(client, email="kitchen2@restaurant.com", role="Kitchen Staff")
    kitchen_user_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]
    assignment = client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/assignments",
        json={"staff_id": kitchen_user_id, "station": "Kitchen"},
        headers=auth_headers(token),
    ).json()

    opened = client.patch(
        f"/staffing/assignments/{assignment['assignment_id']}/attendance",
        json={"attendance_status": "confirmed"},
        headers=auth_headers(token),
    )
    assert opened.json()["attendance_status"] == "confirmed"

    closed = client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/closing-report",
        json={"actual_order_volume": 212, "notes": "Ran short-staffed on Grill after 8pm"},
        headers=auth_headers(token),
    )
    assert closed.status_code == 201

    duplicate = client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/closing-report",
        json={"actual_order_volume": 100},
        headers=auth_headers(token),
    )
    assert duplicate.status_code == 409
