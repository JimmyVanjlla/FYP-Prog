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


def test_deactivated_menu_item_excluded_from_default_listing(client):
    """UC-MR-01 Alt Flow 3a — deactivation removes it from active
    ordering/prep screens while preserving it for reporting."""
    token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Discontinued Dish", "price": "8.00", "category": "Main"},
        headers=auth_headers(token),
    ).json()
    client.delete(f"/menu-items/{item['menu_item_id']}", headers=auth_headers(token))

    default_listing = client.get("/menu-items", headers=auth_headers(token)).json()
    assert item["menu_item_id"] not in [m["menu_item_id"] for m in default_listing]

    with_inactive = client.get(
        "/menu-items", params={"include_inactive": True}, headers=auth_headers(token)
    ).json()
    assert item["menu_item_id"] in [m["menu_item_id"] for m in with_inactive]


def test_remove_recipe_link(client):
    """UC-MR-02 Alt Flow 2a."""
    token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
    ).json()
    link = client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": 4, "quantity_per_serving": "0.180"},
        headers=auth_headers(token),
    ).json()

    resp = client.delete(
        f"/menu-items/{item['menu_item_id']}/recipe-links/{link['link_id']}", headers=auth_headers(token)
    )
    assert resp.status_code == 204

    updated = client.get("/menu-items", headers=auth_headers(token)).json()
    dish = next(m for m in updated if m["menu_item_id"] == item["menu_item_id"])
    assert dish["recipe_links"] == []


def test_remove_recipe_link_404_for_wrong_menu_item(client):
    token = _manager_token(client)
    item_a = client.post(
        "/menu-items", json={"name": "Dish A", "price": "5.00", "category": "Main"}, headers=auth_headers(token)
    ).json()
    item_b = client.post(
        "/menu-items", json={"name": "Dish B", "price": "5.00", "category": "Main"}, headers=auth_headers(token)
    ).json()
    link = client.post(
        f"/menu-items/{item_a['menu_item_id']}/recipe-links",
        json={"ingredient_id": 4, "quantity_per_serving": "0.180"},
        headers=auth_headers(token),
    ).json()

    resp = client.delete(
        f"/menu-items/{item_b['menu_item_id']}/recipe-links/{link['link_id']}", headers=auth_headers(token)
    )
    assert resp.status_code == 404
