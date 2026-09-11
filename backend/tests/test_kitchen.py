from datetime import date
from decimal import Decimal

from app.models.forecasting import Forecast
from tests.conftest import auth_headers, register_and_login


def _manager_token(client):
    return register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")


def _create_menu_item(client, token):
    return client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
    ).json()


def _seed_forecast(db_session, *, menu_item_id: int) -> Forecast:
    """Bypasses Algorithm 1 entirely (no Prophet call) — Kitchen Operations
    tests care about what happens *after* a forecast exists (FR5.x), not
    about re-testing Module 4's training pipeline."""
    forecast = Forecast(
        menu_item_id=menu_item_id,
        meal_period="Lunch",
        forecast_date=date(2026, 8, 21),
        predicted_quantity=Decimal("100.00"),
    )
    db_session.add(forecast)
    db_session.commit()
    db_session.refresh(forecast)
    return forecast


def test_generate_prep_recommendation(client, db_session):
    """FR5.1."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    _seed_forecast(db_session, menu_item_id=item["menu_item_id"])

    resp = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Lunch", "forecast_date": "2026-08-21"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["recommended_quantity"] == "100.00"


def test_generate_prep_recommendation_without_forecast_404s(client):
    token = _manager_token(client)
    item = _create_menu_item(client, token)

    resp = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Dinner", "forecast_date": "2026-08-21"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 404


def test_confirm_prep_within_threshold_needs_no_reason(client, db_session):
    """FR5.2 — small adjustments don't require a justification."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    _seed_forecast(db_session, menu_item_id=item["menu_item_id"])
    reco = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Lunch", "forecast_date": "2026-08-21"},
        headers=auth_headers(token),
    ).json()

    kitchen_token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    # Default prep_deviation_threshold is 10%; 100 -> 105 is only 5%.
    resp = client.post(
        f"/kitchen/prep-recommendations/{reco['recommendation_id']}/confirm",
        json={"confirmed_quantity": "105.00"},
        headers=auth_headers(kitchen_token),
    )
    assert resp.status_code == 201


def test_confirm_prep_beyond_threshold_requires_reason(client, db_session):
    """FR5.5."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    _seed_forecast(db_session, menu_item_id=item["menu_item_id"])
    reco = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Lunch", "forecast_date": "2026-08-21"},
        headers=auth_headers(token),
    ).json()

    kitchen_token = register_and_login(client, email="kitchen2@restaurant.com", role="Kitchen Staff")
    # 100 -> 150 is a 50% deviation, well past the 10% default threshold.
    without_reason = client.post(
        f"/kitchen/prep-recommendations/{reco['recommendation_id']}/confirm",
        json={"confirmed_quantity": "150.00"},
        headers=auth_headers(kitchen_token),
    )
    assert without_reason.status_code == 422

    with_reason = client.post(
        f"/kitchen/prep-recommendations/{reco['recommendation_id']}/confirm",
        json={"confirmed_quantity": "150.00", "deviation_reason": "Local event nearby, expecting higher walk-in"},
        headers=auth_headers(kitchen_token),
    )
    assert with_reason.status_code == 201


def test_log_leftover(client):
    """FR5.3."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    kitchen_token = register_and_login(client, email="kitchen3@restaurant.com", role="Kitchen Staff")

    resp = client.post(
        "/kitchen/leftover-logs",
        json={
            "menu_item_id": item["menu_item_id"],
            "service_period_date": "2026-08-14",
            "prepared_quantity": "150.00",
            "leftover_quantity": "12.00",
            "leftover_level": "Partially Eaten",
        },
        headers=auth_headers(kitchen_token),
    )
    assert resp.status_code == 201


def test_leftover_cannot_exceed_prepared(client):
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    kitchen_token = register_and_login(client, email="kitchen4@restaurant.com", role="Kitchen Staff")

    resp = client.post(
        "/kitchen/leftover-logs",
        json={
            "menu_item_id": item["menu_item_id"],
            "service_period_date": "2026-08-14",
            "prepared_quantity": "10.00",
            "leftover_quantity": "50.00",
            "leftover_level": "Mostly Uneaten",
        },
        headers=auth_headers(kitchen_token),
    )
    assert resp.status_code == 422


def test_notification_queued_when_fcm_not_configured(client, db_session):
    """FR5.4 — a significant deviation triggers a notification to Kitchen
    Staff; without real FCM credentials it's honestly stored as
    queued_for_retry rather than faked as sent."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    _seed_forecast(db_session, menu_item_id=item["menu_item_id"])
    reco = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Lunch", "forecast_date": "2026-08-21"},
        headers=auth_headers(token),
    ).json()

    kitchen_token = register_and_login(client, email="kitchen5@restaurant.com", role="Kitchen Staff")
    client.post(
        f"/kitchen/prep-recommendations/{reco['recommendation_id']}/confirm",
        json={"confirmed_quantity": "150.00", "deviation_reason": "Local event"},
        headers=auth_headers(kitchen_token),
    )

    notifications = client.get("/kitchen/notifications", headers=auth_headers(kitchen_token)).json()
    assert len(notifications) == 1
    assert notifications[0]["status"] == "queued_for_retry"
    assert notifications[0]["type"] == "prep_update"
