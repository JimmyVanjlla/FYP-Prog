"""FR2.4: "automatically flagging items whose ingredients fall below
threshold". Separate from availability, which only flips once stock can't
cover a single serving."""
from tests.conftest import auth_headers, register_and_login


def _dish_with_ingredient(client, *, stock, threshold=None):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    inventory = auth_headers(register_and_login(client, email="inv@restaurant.com", role="Inventory Staff"))
    payload = {"name": "Rice", "unit": "kg", "current_stock": stock}
    if threshold is not None:
        payload["low_stock_threshold"] = threshold
    ingredient = client.post("/inventory/ingredients", json=payload, headers=inventory).json()
    item = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager
    ).json()
    client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity_per_serving": "0.2"},
        headers=manager,
    )
    return manager, item


def _menu_entry(client, headers, item):
    return next(m for m in client.get("/menu-items", headers=headers).json() if m["menu_item_id"] == item["menu_item_id"])


def test_item_is_flagged_while_still_available_when_an_ingredient_is_under_the_default_threshold(client):
    # System default threshold is 10; 5 kg is under it but plenty for a 0.2 kg serving.
    manager, item = _dish_with_ingredient(client, stock="5")

    entry = _menu_entry(client, manager, item)

    assert entry["has_low_stock_ingredient"] is True
    assert entry["is_available"] is True


def test_ingredient_specific_threshold_overrides_the_default(client):
    # Own threshold of 2 kg: 5 kg on hand is fine even though it's under the default of 10.
    manager, item = _dish_with_ingredient(client, stock="5", threshold="2")

    assert _menu_entry(client, manager, item)["has_low_stock_ingredient"] is False


def test_well_stocked_item_is_not_flagged(client):
    manager, item = _dish_with_ingredient(client, stock="50")

    entry = _menu_entry(client, manager, item)

    assert entry["has_low_stock_ingredient"] is False
    assert entry["is_available"] is True


def test_item_without_a_recipe_is_not_flagged(client):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    item = client.post(
        "/menu-items", json={"name": "Teh Tarik", "price": "2.50", "category": "Beverage"}, headers=manager
    ).json()

    assert _menu_entry(client, manager, item)["has_low_stock_ingredient"] is False
