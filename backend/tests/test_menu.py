from tests.conftest import auth_headers, register_and_login


def _manager_token(client):
    return register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")


def test_manager_can_create_menu_item(client):
    """FR2.1."""
    token = _manager_token(client)
    resp = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Nasi Lemak Ayam"
    assert body["is_active"] is True
    assert body["is_available"] is True  # stubbed until Sprint 2


def test_non_manager_cannot_create_menu_item(client):
    """FR1.3 RBAC applied to Module 2."""
    token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    resp = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


def test_zero_price_is_rejected(client):
    """FR2.5."""
    token = _manager_token(client)
    resp = client.post(
        "/menu-items",
        json={"name": "Free Item", "price": "0", "category": "Main"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


def test_negative_price_is_rejected(client):
    """FR2.5."""
    token = _manager_token(client)
    resp = client.post(
        "/menu-items",
        json={"name": "Negative Item", "price": "-5.00", "category": "Main"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


def test_non_numeric_price_is_rejected(client):
    """FR2.5."""
    token = _manager_token(client)
    resp = client.post(
        "/menu-items",
        json={"name": "Bad Item", "price": "not-a-number", "category": "Main"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


def test_any_authenticated_role_can_list_menu_items(client):
    """FR2.4 — read access isn't restricted to managers."""
    manager_token = _manager_token(client)
    client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(manager_token),
    )
    kitchen_token = register_and_login(client, email="kitchen2@restaurant.com", role="Kitchen Staff")
    resp = client.get("/menu-items", headers=auth_headers(kitchen_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_recipe_link_zero_quantity_is_rejected(client):
    """FR2.2 / FR2.5."""
    token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
    ).json()

    resp = client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": 1, "quantity_per_serving": "0"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


def test_recipe_link_valid_quantity_is_created(client):
    """FR2.2."""
    token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
    ).json()

    resp = client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": 4, "quantity_per_serving": "0.180"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["ingredient_id"] == 4


def test_deactivate_menu_item(client):
    """FR2.1 — deactivate rather than hard-delete."""
    token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
    ).json()

    resp = client.delete(f"/menu-items/{item['menu_item_id']}", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
