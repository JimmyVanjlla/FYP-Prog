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


def test_manual_prep_quantity_when_no_forecast(client):
    """UC-KO-01 Alt Flow 3a — manual_quantity fallback instead of a dead end."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)

    resp = client.post(
        "/kitchen/prep-recommendations",
        json={
            "menu_item_id": item["menu_item_id"],
            "meal_period": "Dinner",
            "forecast_date": "2026-08-21",
            "manual_quantity": "40",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["forecast_id"] is None
    assert body["recommended_quantity"] == "40.00"


def test_prep_recommendation_rejected_for_inactive_menu_item(client, db_session):
    """UC-MR-01 Alt Flow 3a — a deactivated item is removed from prep
    recommendation screens."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    _seed_forecast(db_session, menu_item_id=item["menu_item_id"])
    client.delete(f"/menu-items/{item['menu_item_id']}", headers=auth_headers(token))

    resp = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Lunch", "forecast_date": "2026-08-21"},
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
    # Registered before the recommendation is generated, so the
    # UC-KO-04-step-1 notification fan-out (by role) actually has a
    # Kitchen Staff recipient to find.
    kitchen_token = register_and_login(client, email="kitchen5@restaurant.com", role="Kitchen Staff")
    reco = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Lunch", "forecast_date": "2026-08-21"},
        headers=auth_headers(token),
    ).json()

    client.post(
        f"/kitchen/prep-recommendations/{reco['recommendation_id']}/confirm",
        json={"confirmed_quantity": "150.00", "deviation_reason": "Local event"},
        headers=auth_headers(kitchen_token),
    )

    notifications = client.get("/kitchen/notifications", headers=auth_headers(kitchen_token)).json()
    # One from generating the recommendation (UC-KO-04 main flow step 1),
    # one from confirming it with a significant deviation (FR5.4).
    assert len(notifications) == 2
    assert all(n["status"] == "queued_for_retry" for n in notifications)
    assert all(n["type"] == "prep_update" for n in notifications)


def test_list_prep_recommendations(client, db_session):
    """FR5.1/FR5.2 — previously only visible once, in the POST response
    that created it."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    _seed_forecast(db_session, menu_item_id=item["menu_item_id"])
    client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": item["menu_item_id"], "meal_period": "Lunch", "forecast_date": "2026-08-21"},
        headers=auth_headers(token),
    )

    resp = client.get("/kitchen/prep-recommendations", headers=auth_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["menu_item_id"] == item["menu_item_id"]
