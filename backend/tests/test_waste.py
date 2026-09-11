from tests.conftest import auth_headers, register_and_login


def _manager_token(client):
    return register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")


def test_leftover_log_generates_waste_log_entries(client):
    """FR6.1 / FR6.2 — logging a leftover fans out into one WasteLog per
    recipe ingredient."""
    manager_token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(manager_token),
    ).json()

    inv_token = register_and_login(client, email="inv@restaurant.com", role="Inventory Staff")
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Chicken Thigh", "unit": "kg", "current_stock": "20"},
        headers=auth_headers(inv_token),
    ).json()
    client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity_per_serving": "0.2"},
        headers=auth_headers(manager_token),
    )

    kitchen_token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    client.post(
        "/kitchen/leftover-logs",
        json={
            "menu_item_id": item["menu_item_id"],
            "service_period_date": "2026-08-14",
            "prepared_quantity": "150.00",
            "leftover_quantity": "10.00",
            "leftover_level": "Partially Eaten",
        },
        headers=auth_headers(kitchen_token),
    )

    logs = client.get("/waste/logs", headers=auth_headers(manager_token)).json()
    assert len(logs) == 1
    assert logs[0]["source_type"] == "leftover"
    assert logs[0]["ingredient_id"] == ingredient["ingredient_id"]
    # 10 servings leftover * 0.2 kg/serving = 2.0 kg wasted.
    assert logs[0]["quantity_wasted"] == "2.000"


def test_waste_trend_aggregation(client):
    """FR6.3."""
    token = _manager_token(client)
    resp = client.post(
        "/waste/trends",
        json={"period_start": "2026-08-01", "period_end": "2026-08-31"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    assert "total_waste_cost" in resp.json()
