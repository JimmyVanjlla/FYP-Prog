from tests.conftest import auth_headers, register_and_login


def _inventory_staff_token(client):
    return register_and_login(client, email="inv@restaurant.com", role="Inventory Staff")


def test_create_ingredient(client):
    """FR3.1."""
    token = _inventory_staff_token(client)
    resp = client.post(
        "/inventory/ingredients",
        json={"name": "Chicken Thigh", "unit": "kg", "current_stock": "4.2"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Chicken Thigh"


def test_low_stock_flag_uses_system_default_when_no_override(client):
    """FR3.3 — SystemConfig.default_low_stock_threshold is 10 by default."""
    token = _inventory_staff_token(client)
    resp = client.post(
        "/inventory/ingredients",
        json={"name": "Rice", "unit": "kg", "current_stock": "5"},
        headers=auth_headers(token),
    )
    assert resp.json()["is_low_stock"] is True  # 5 < default threshold of 10

    resp2 = client.post(
        "/inventory/ingredients",
        json={"name": "Salt", "unit": "kg", "current_stock": "50"},
        headers=auth_headers(token),
    )
    assert resp2.json()["is_low_stock"] is False


def test_ingredient_specific_threshold_overrides_default(client):
    """FR3.3."""
    token = _inventory_staff_token(client)
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Chili", "unit": "kg", "current_stock": "3"},
        headers=auth_headers(token),
    ).json()
    assert ingredient["is_low_stock"] is True  # 3 < default 10

    resp = client.patch(
        f"/inventory/ingredients/{ingredient['ingredient_id']}/threshold",
        json={"low_stock_threshold": "1"},
        headers=auth_headers(token),
    )
    assert resp.json()["is_low_stock"] is False  # 3 >= override of 1


def test_stock_adjustment_updates_running_total(client):
    """FR3.4."""
    token = _inventory_staff_token(client)
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Onion", "unit": "kg", "current_stock": "10"},
        headers=auth_headers(token),
    ).json()

    resp = client.post(
        "/inventory/stock-adjustments",
        json={
            "ingredient_id": ingredient["ingredient_id"],
            "adjusted_quantity": "-2.5",
            "reason_category": "spoilage",
            "note": "left out overnight",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201

    updated = client.get("/inventory/ingredients", headers=auth_headers(token)).json()
    onion = next(i for i in updated if i["ingredient_id"] == ingredient["ingredient_id"])
    assert onion["current_stock"] == "7.500"


def test_stock_adjustment_rejects_negative_result(client):
    """FR3.6."""
    token = _inventory_staff_token(client)
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Garlic", "unit": "kg", "current_stock": "1"},
        headers=auth_headers(token),
    ).json()

    resp = client.post(
        "/inventory/stock-adjustments",
        json={
            "ingredient_id": ingredient["ingredient_id"],
            "adjusted_quantity": "-5",
            "reason_category": "spillage",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


def test_stock_adjustment_rejects_zero_quantity(client):
    """FR3.6."""
    token = _inventory_staff_token(client)
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Pepper", "unit": "kg", "current_stock": "5"},
        headers=auth_headers(token),
    ).json()

    resp = client.post(
        "/inventory/stock-adjustments",
        json={"ingredient_id": ingredient["ingredient_id"], "adjusted_quantity": "0", "reason_category": "miscount"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


def test_kitchen_staff_can_submit_restocking_request(client):
    """FR3.5."""
    inv_token = _inventory_staff_token(client)
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Flour", "unit": "kg", "current_stock": "5"},
        headers=auth_headers(inv_token),
    ).json()

    kitchen_token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    resp = client.post(
        "/inventory/restocking-requests",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity": "10", "urgency": True},
        headers=auth_headers(kitchen_token),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


def test_non_kitchen_staff_cannot_submit_restocking_request(client):
    """FR1.3 RBAC applied to Module 3."""
    token = _inventory_staff_token(client)
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Sugar", "unit": "kg", "current_stock": "5"},
        headers=auth_headers(token),
    ).json()

    resp = client.post(
        "/inventory/restocking-requests",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity": "10"},
        headers=auth_headers(token),  # Inventory Staff, not Kitchen Staff
    )
    assert resp.status_code == 403


def test_record_stock_batch_adds_to_current_stock(client):
    """FR3.1 / FR3.2."""
    token = _inventory_staff_token(client)
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Milk", "unit": "litre", "current_stock": "0"},
        headers=auth_headers(token),
    ).json()

    resp = client.post(
        "/inventory/stock-batches",
        json={
            "ingredient_id": ingredient["ingredient_id"],
            "quantity": "20",
            "received_date": "2026-08-10",
            "expiry_date": "2026-08-17",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201

    updated = client.get("/inventory/ingredients", headers=auth_headers(token)).json()
    milk = next(i for i in updated if i["ingredient_id"] == ingredient["ingredient_id"])
    assert milk["current_stock"] == "20.000"
