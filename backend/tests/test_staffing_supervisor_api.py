"""What the Schedule Builder screen needs from the staffing API."""
from datetime import date
from decimal import Decimal

from app.models.forecasting import Forecast
from tests.conftest import auth_headers, register_and_login


def _supervisor(client):
    return auth_headers(register_and_login(client, email="supervisor@restaurant.com", role="Shift Supervisor"))


def test_supervisor_can_list_assignable_staff(client):
    """FR8.2: GET /users is Manager-only, so the supervisor had no way to
    find a staff_id to assign."""
    supervisor = _supervisor(client)
    register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    register_and_login(client, email="owner@restaurant.com", role="Restaurant Owner")

    staff = client.get("/staffing/staff", headers=supervisor).json()
    roles = {s["role"] for s in staff}

    assert "Kitchen Staff" in roles
    assert "Restaurant Owner" not in roles  # the Owner doesn't work a station
    # Only what's needed to pick someone: no emails or password hashes.
    assert all(set(s) == {"user_id", "name", "role"} for s in staff)


def test_staff_list_excludes_deactivated_accounts(client):
    supervisor = _supervisor(client)
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    kitchen_user = next(u for u in client.get("/users", headers=manager).json() if u["role"] == "Kitchen Staff")
    client.patch(f"/users/{kitchen_user['user_id']}", json={"is_active": False}, headers=manager)

    staff = client.get("/staffing/staff", headers=supervisor).json()

    assert kitchen_user["user_id"] not in {s["user_id"] for s in staff}


def test_kitchen_staff_cannot_list_assignable_staff(client):
    token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    assert client.get("/staffing/staff", headers=auth_headers(token)).status_code == 403


def test_regenerating_recommendations_replaces_rather_than_stacks(client):
    supervisor = _supervisor(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-09-01", "meal_period": "Lunch"}, headers=supervisor
    ).json()
    url = f"/staffing/schedules/{schedule['schedule_id']}/recommendations"

    client.post(url, headers=supervisor)
    client.post(url, headers=supervisor)

    # Kitchen + Front of House, once each.
    assert len(client.get(url, headers=supervisor).json()) == 2


def test_closing_report_compares_actual_to_forecast(client, db_session):
    """FR8.4: "actual vs. forecasted performance"."""
    supervisor = _supervisor(client)
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    item = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager
    ).json()
    day = date(2026, 9, 2)
    db_session.add(
        Forecast(
            menu_item_id=item["menu_item_id"],
            meal_period="Lunch",
            forecast_date=day,
            predicted_quantity=Decimal("100.00"),
        )
    )
    db_session.commit()
    schedule = client.post(
        "/staffing/schedules", json={"date": day.isoformat(), "meal_period": "Lunch"}, headers=supervisor
    ).json()
    sid = schedule["schedule_id"]

    assert client.get(f"/staffing/schedules/{sid}/closing-report", headers=supervisor).status_code == 404

    submitted = client.post(
        f"/staffing/schedules/{sid}/closing-report",
        json={"actual_order_volume": 90, "notes": "Quiet start"},
        headers=supervisor,
    ).json()
    assert submitted["forecasted_volume"] == 100
    assert submitted["variance"] == -10

    fetched = client.get(f"/staffing/schedules/{sid}/closing-report", headers=supervisor).json()
    assert fetched["forecasted_volume"] == 100 and fetched["variance"] == -10


def test_closing_report_without_a_forecast_has_no_comparison(client):
    supervisor = _supervisor(client)
    schedule = client.post(
        "/staffing/schedules", json={"date": "2026-09-05", "meal_period": "Dinner"}, headers=supervisor
    ).json()
    submitted = client.post(
        f"/staffing/schedules/{schedule['schedule_id']}/closing-report",
        json={"actual_order_volume": 70},
        headers=supervisor,
    ).json()
    assert submitted["forecasted_volume"] is None
    assert submitted["variance"] is None
