"""FR6.5: "reject waste log entries with negative quantities, or quantities
exceeding the originally prepared or delivered amount"."""
from datetime import date, timedelta

from tests.conftest import auth_headers, register_and_login


def _setup(client):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    inventory = auth_headers(register_and_login(client, email="inv@restaurant.com", role="Inventory Staff"))
    kitchen = auth_headers(register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff"))

    ingredient = client.post(
        "/inventory/ingredients", json={"name": "Chicken", "unit": "kg", "current_stock": "20"}, headers=inventory
    ).json()
    other = client.post(
        "/inventory/ingredients", json={"name": "Rice", "unit": "kg", "current_stock": "20"}, headers=inventory
    ).json()
    batch = client.post(
        "/inventory/stock-batches",
        json={
            "ingredient_id": ingredient["ingredient_id"],
            "quantity": "5",
            "received_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=2)).isoformat(),
        },
        headers=inventory,
    ).json()
    item = client.post(
        "/menu-items", json={"name": "Chicken Rice", "price": "7.00", "category": "Rice"}, headers=manager
    ).json()
    client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity_per_serving": "0.2"},
        headers=manager,
    )
    leftover = client.post(
        "/kitchen/leftover-logs",
        json={
            "menu_item_id": item["menu_item_id"],
            "service_period_date": date.today().isoformat(),
            "prepared_quantity": "10",
            "leftover_quantity": "1",
            "leftover_level": "Partially Eaten",
        },
        headers=kitchen,
    ).json()
    return {
        "inventory": inventory,
        "kitchen": kitchen,
        "ingredient": ingredient,
        "other": other,
        "batch": batch,
        "leftover": leftover,
    }


def _expiry(ctx, quantity, **overrides):
    return {
        "source_type": "expiry",
        "source_ref_id": ctx["batch"]["batch_id"],
        "ingredient_id": ctx["ingredient"]["ingredient_id"],
        "quantity_wasted": quantity,
        **overrides,
    }


def test_expiry_waste_within_the_delivered_amount_is_accepted_and_costed(client):
    ctx = _setup(client)

    resp = client.post("/waste/logs", json=_expiry(ctx, "3"), headers=ctx["inventory"])

    assert resp.status_code == 201
    body = resp.json()
    assert body["source_type"] == "expiry"
    assert body["quantity_wasted"] == "3.000"
    assert "waste_cost" in body


def test_expiry_waste_beyond_the_delivered_amount_is_rejected(client):
    ctx = _setup(client)

    resp = client.post("/waste/logs", json=_expiry(ctx, "6"), headers=ctx["inventory"])

    assert resp.status_code == 422
    assert "delivered" in resp.json()["detail"]


def test_negative_or_zero_quantity_is_rejected(client):
    ctx = _setup(client)
    assert client.post("/waste/logs", json=_expiry(ctx, "-1"), headers=ctx["inventory"]).status_code == 422
    assert client.post("/waste/logs", json=_expiry(ctx, "0"), headers=ctx["inventory"]).status_code == 422


def test_batch_of_a_different_ingredient_is_rejected(client):
    ctx = _setup(client)
    body = _expiry(ctx, "1", ingredient_id=ctx["other"]["ingredient_id"])
    assert client.post("/waste/logs", json=body, headers=ctx["inventory"]).status_code == 422


def test_unknown_source_record_is_rejected(client):
    ctx = _setup(client)
    assert client.post("/waste/logs", json=_expiry(ctx, "1", source_ref_id=9999), headers=ctx["inventory"]).status_code == 422


def test_leftover_waste_is_capped_at_what_was_prepared(client):
    ctx = _setup(client)
    leftover_id = ctx["leftover"]["log_id"]
    ingredient_id = ctx["ingredient"]["ingredient_id"]

    # 10 servings prepared x 0.2 kg = 2.0 kg of chicken prepared.
    ok = client.post(
        "/waste/logs",
        json={"source_type": "leftover", "source_ref_id": leftover_id, "ingredient_id": ingredient_id, "quantity_wasted": "1.5"},
        headers=ctx["kitchen"],
    )
    too_much = client.post(
        "/waste/logs",
        json={"source_type": "leftover", "source_ref_id": leftover_id, "ingredient_id": ingredient_id, "quantity_wasted": "2.5"},
        headers=ctx["kitchen"],
    )

    assert ok.status_code == 201
    assert too_much.status_code == 422
    assert "prepared" in too_much.json()["detail"]


def test_only_kitchen_inventory_and_manager_can_log_waste(client):
    ctx = _setup(client)
    delivery = auth_headers(register_and_login(client, email="delivery@restaurant.com", role="Delivery/Logistics Staff"))
    assert client.post("/waste/logs", json=_expiry(ctx, "1"), headers=delivery).status_code == 403
