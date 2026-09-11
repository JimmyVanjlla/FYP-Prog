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


def test_list_staffing_recommendations_after_generation(client):
    """FR8.1 — recommendations were previously only ever visible once, in
    the POST response that created them."""
    token = _supervisor_token(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-09-01", "meal_period": "Lunch"}, headers=auth_headers(token)
    ).json()
    client.post(f"/staffing/schedules/{schedule['schedule_id']}/recommendations", headers=auth_headers(token))

    resp = client.get(f"/staffing/schedules/{schedule['schedule_id']}/recommendations", headers=auth_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2  # Kitchen + Front of House


def test_list_shift_assignments_after_assigning(client):
    """FR8.2 — "who's on this shift", viewable after the fact."""
    token = _supervisor_token(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-08-22", "meal_period": "Dinner"}, headers=auth_headers(token)
    ).json()
    kitchen_token = register_and_login(client, email="kitchen3@restaurant.com", role="Kitchen Staff")
    kitchen_user_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]
    client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/assignments",
        json={"staff_id": kitchen_user_id, "station": "Kitchen"},
        headers=auth_headers(token),
    )

    resp = client.get(f"/staffing/schedules/{schedule['schedule_id']}/assignments", headers=auth_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["staff_id"] == kitchen_user_id


def test_my_schedule_only_shows_published_assignments(client):
    """UC-SS-05 "View My Shift Schedule" — a staff member's own shifts,
    without needing a schedule_id; drafts don't count as "my schedule"
    yet."""
    supervisor_token = _supervisor_token(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-08-22", "meal_period": "Dinner"}, headers=auth_headers(supervisor_token)
    ).json()
    kitchen_token = register_and_login(client, email="kitchen4@restaurant.com", role="Kitchen Staff")
    kitchen_user_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]
    client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/assignments",
        json={"staff_id": kitchen_user_id, "station": "Kitchen"},
        headers=auth_headers(supervisor_token),
    )

    before_publish = client.get("/staffing/my-schedule", headers=auth_headers(kitchen_token)).json()
    assert before_publish == []

    client.post(f"/staffing/schedules/{schedule['schedule_id']}/publish", headers=auth_headers(supervisor_token))

    after_publish = client.get("/staffing/my-schedule", headers=auth_headers(kitchen_token)).json()
    assert len(after_publish) == 1
    assert after_publish[0]["date"] == "2026-08-22"
    assert after_publish[0]["station"] == "Kitchen"


def test_publish_schedule_notifies_assigned_staff(client):
    """UC-SS-02 main flow step 5."""
    supervisor_token = _supervisor_token(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-08-23", "meal_period": "Lunch"}, headers=auth_headers(supervisor_token)
    ).json()
    kitchen_token = register_and_login(client, email="kitchen5@restaurant.com", role="Kitchen Staff")
    kitchen_user_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]
    client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/assignments",
        json={"staff_id": kitchen_user_id, "station": "Kitchen"},
        headers=auth_headers(supervisor_token),
    )

    client.post(f"/staffing/schedules/{schedule['schedule_id']}/publish", headers=auth_headers(supervisor_token))

    notifications = client.get("/kitchen/notifications", headers=auth_headers(kitchen_token)).json()
    assert len(notifications) == 1
    assert notifications[0]["type"] == "shift_published"


def test_publish_schedule_logs_staffing_deviation(client):
    """UC-SS-02 Alt Flow 3a — assigning fewer/more staff than the AI
    recommendation is logged for later comparison."""
    supervisor_token = _supervisor_token(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-09-05", "meal_period": "Lunch"}, headers=auth_headers(supervisor_token)
    ).json()
    # No forecast exists, so the recommendation falls back to 0 staff per
    # station (per test_staffing_recommendation_falls_back_with_no_forecast).
    client.post(f"/staffing/schedules/{schedule['schedule_id']}/recommendations", headers=auth_headers(supervisor_token))

    kitchen_token = register_and_login(client, email="kitchen6@restaurant.com", role="Kitchen Staff")
    kitchen_user_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]
    client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/assignments",
        json={"staff_id": kitchen_user_id, "station": "Kitchen"},
        headers=auth_headers(supervisor_token),
    )
    client.post(f"/staffing/schedules/{schedule['schedule_id']}/publish", headers=auth_headers(supervisor_token))

    manager_token = register_and_login(client, email="manager_audit@restaurant.com", role="Restaurant Manager")
    audit = client.get("/users/audit-logs", headers=auth_headers(manager_token)).json()
    assert any("staffing_deviation" in entry["action"] and "station=Kitchen" in entry["action"] for entry in audit)
