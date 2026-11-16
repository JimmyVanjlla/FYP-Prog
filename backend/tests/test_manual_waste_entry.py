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


def _stock(client, ctx):
    rows = client.get("/inventory/ingredients", headers=ctx["inventory"]).json()
    return next(r for r in rows if r["ingredient_id"] == ctx["ingredient"]["ingredient_id"])["current_stock"]


def _batches(client, ctx):
    return client.get(
        f"/inventory/stock-batches?ingredient_id={ctx['ingredient']['ingredient_id']}", headers=ctx["inventory"]
    ).json()


def test_wasting_a_whole_expiring_batch_takes_it_off_stock_and_off_the_screen(client):
    ctx = _setup(client)
    assert float(_stock(client, ctx)) == 25.0  # 20 in stock + the 5 kg batch

    resp = client.post("/waste/logs", json=_expiry(ctx, "5"), headers=ctx["inventory"])

    assert resp.status_code == 201
    assert float(_stock(client, ctx)) == 20.0
    assert _batches(client, ctx) == []  # the batch, and its near-expiry alert, are gone
    adjustments = client.get(
        f"/inventory/stock-adjustments?ingredient_id={ctx['ingredient']['ingredient_id']}", headers=ctx["inventory"]
    ).json()
    assert [(float(a["adjusted_quantity"]), a["reason_category"]) for a in adjustments] == [(-5.0, "spoilage")]
    logs = client.get(f"/waste/logs?ingredient_id={ctx['ingredient']['ingredient_id']}", headers=ctx["inventory"]).json()
    assert [(l["source_type"], float(l["quantity_wasted"])) for l in logs if l["source_type"] == "expiry"] == [("expiry", 5.0)]


def test_wasting_part_of_a_batch_leaves_the_rest(client):
    ctx = _setup(client)

    assert client.post("/waste/logs", json=_expiry(ctx, "2"), headers=ctx["inventory"]).status_code == 201

    assert float(_stock(client, ctx)) == 23.0
    batches = _batches(client, ctx)
    assert len(batches) == 1 and float(batches[0]["quantity"]) == 3.0
    # the rest can still be wasted, and then the batch goes
    assert client.post("/waste/logs", json=_expiry(ctx, "3"), headers=ctx["inventory"]).status_code == 201
    assert _batches(client, ctx) == []


def test_wasting_a_batch_never_drives_stock_below_zero(client):
    ctx = _setup(client)
    # someone already corrected the count down to 2 kg, less than the 5 kg batch
    client.post(
        "/inventory/stock-adjustments",
        json={"ingredient_id": ctx["ingredient"]["ingredient_id"], "adjusted_quantity": "-23", "reason_category": "miscount"},
        headers=ctx["inventory"],
    )
    assert float(_stock(client, ctx)) == 2.0

    assert client.post("/waste/logs", json=_expiry(ctx, "5"), headers=ctx["inventory"]).status_code == 201

    assert float(_stock(client, ctx)) == 0.0
    assert _batches(client, ctx) == []


def test_leftover_waste_does_not_touch_stock(client):
    ctx = _setup(client)
    body = {
        "source_type": "leftover",
        "source_ref_id": ctx["leftover"]["log_id"],
        "ingredient_id": ctx["ingredient"]["ingredient_id"],
        "quantity_wasted": "1",
    }
    assert client.post("/waste/logs", json=body, headers=ctx["kitchen"]).status_code == 201
    assert float(_stock(client, ctx)) == 25.0


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
