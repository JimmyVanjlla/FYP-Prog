from datetime import date, timedelta

from tests.conftest import auth_headers, register_and_login


def _manager_token(client):
    return register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")


def _create_menu_item(client, token):
    return client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
    ).json()


def test_record_order(client):
    """FR4.1's raw input."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)

    resp = client.post(
        "/forecasting/orders",
        json={
            "menu_item_id": item["menu_item_id"],
            "quantity": 3,
            "meal_period": "Lunch",
            "order_date": "2026-08-14",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201


def test_training_skips_item_with_insufficient_data(client):
    """FR4.6 / UC-DF-02 Alt Flow 2a — fewer than MIN_DATA_POINTS orders
    means the item is flagged rather than forced through a fit."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)

    # Only 3 days of data — well under MIN_DATA_POINTS (14).
    base = date(2026, 8, 1)
    for i in range(3):
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": 5,
                "meal_period": "Lunch",
                "order_date": (base + timedelta(days=i)).isoformat(),
            },
            headers=auth_headers(token),
        )

    resp = client.post("/forecasting/train", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["forecasts_created"] == 0
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["reason"] == "insufficient_data"


def test_training_generates_forecasts_with_enough_data(client):
    """FR4.1-FR4.3 — full pipeline: aggregate orders, train Prophet, store
    Forecast rows for the item/meal-period."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)

    # Ends yesterday (relative to whenever this test actually runs), not a
    # hardcoded date — train_and_generate_forecasts only stores rows for
    # forecast_date > today, so historical data has to actually be in the
    # past relative to the real clock for any forecast rows to be created.
    base = date.today() - timedelta(days=30)
    for i in range(30):  # comfortably over MIN_DATA_POINTS
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": 40 + (i % 7),  # mild weekly pattern for Prophet to pick up
                "meal_period": "Lunch",
                "order_date": (base + timedelta(days=i)).isoformat(),
            },
            headers=auth_headers(token),
        )

    resp = client.post("/forecasting/train", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["forecasts_created"] > 0
    assert body["skipped"] == []

    forecasts = client.get(
        "/forecasting/forecasts", params={"menu_item_id": item["menu_item_id"]}, headers=auth_headers(token)
    ).json()
    assert len(forecasts) == body["forecasts_created"]
    assert all(f["meal_period"] == "Lunch" for f in forecasts)
    assert all(float(f["predicted_quantity"]) >= 0 for f in forecasts)


def test_non_manager_cannot_trigger_training(client):
    """FR1.3 RBAC applied to Module 4."""
    token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    resp = client.post("/forecasting/train", headers=auth_headers(token))
    assert resp.status_code == 403
