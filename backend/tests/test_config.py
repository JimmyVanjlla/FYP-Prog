from tests.conftest import auth_headers, register_and_login


def _manager_token(client):
    return register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")


def test_read_config_defaults(client):
    token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    resp = client.get("/config", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["leftover_rate_threshold"] == "15.00"
    assert body["default_low_stock_threshold"] == "10.000"


def test_manager_can_update_config(client):
    """FR3.3 / FR7.5 / Ch3 §3.4.2's "configure system settings"."""
    token = _manager_token(client)
    resp = client.patch(
        "/config",
        json={"default_low_stock_threshold": "20", "leftover_rate_threshold": "25"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_low_stock_threshold"] == "20.000"
    assert body["leftover_rate_threshold"] == "25.00"
    # Untouched fields keep their previous value, not reset to a default.
    assert body["prep_deviation_threshold"] == "10.00"


def test_non_manager_cannot_update_config(client):
    """FR1.3 RBAC applied to the config endpoint."""
    token = register_and_login(client, email="inv@restaurant.com", role="Inventory Staff")
    resp = client.patch(
        "/config", json={"default_low_stock_threshold": "5"}, headers=auth_headers(token)
    )
    assert resp.status_code == 403


def test_leftover_rate_threshold_rejects_over_100(client):
    """FR7.5 — explicitly 0-100%."""
    token = _manager_token(client)
    resp = client.patch("/config", json={"leftover_rate_threshold": "150"}, headers=auth_headers(token))
    assert resp.status_code == 422


def test_leftover_rate_threshold_rejects_negative(client):
    """FR7.5."""
    token = _manager_token(client)
    resp = client.patch("/config", json={"leftover_rate_threshold": "-5"}, headers=auth_headers(token))
    assert resp.status_code == 422


def test_default_low_stock_threshold_rejects_negative(client):
    """FR3.3 — same spirit as FR3.6's rejection of negative thresholds."""
    token = _manager_token(client)
    resp = client.patch(
        "/config", json={"default_low_stock_threshold": "-1"}, headers=auth_headers(token)
    )
    assert resp.status_code == 422


def test_updated_threshold_actually_changes_downstream_behavior(client):
    """Confirms this isn't just a config value sitting unused — raising
    the system-wide default low-stock threshold immediately changes which
    ingredients Module 3 flags as low stock."""
    manager_token = _manager_token(client)
    inv_token = register_and_login(client, email="inv@restaurant.com", role="Inventory Staff")

    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Rice", "unit": "kg", "current_stock": "12"},
        headers=auth_headers(inv_token),
    ).json()
    assert ingredient["is_low_stock"] is False  # 12 >= default threshold of 10

    client.patch(
        "/config", json={"default_low_stock_threshold": "15"}, headers=auth_headers(manager_token)
    )

    updated = client.get("/inventory/ingredients", headers=auth_headers(inv_token)).json()
    rice = next(i for i in updated if i["ingredient_id"] == ingredient["ingredient_id"])
    assert rice["is_low_stock"] is True  # 12 < new threshold of 15
