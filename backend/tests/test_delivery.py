from tests.conftest import auth_headers, register_and_login


def _setup_po(client):
    officer_token = register_and_login(client, email="officer@restaurant.com", role="Procurement Officer")
    supplier = client.post(
        "/procurement/suppliers",
        json={"name": "Fresh Farm Supplies", "contact_info": "+60 12-345 6789"},
        headers=auth_headers(officer_token),
    ).json()
    inv_token = register_and_login(client, email="inv@restaurant.com", role="Inventory Staff")
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Chicken Thigh", "unit": "kg", "current_stock": "5"},
        headers=auth_headers(inv_token),
    ).json()
    client.post(
        "/procurement/suppliers/pricing",
        json={
            "supplier_id": supplier["supplier_id"],
            "ingredient_id": ingredient["ingredient_id"],
            "unit_price": "9.20",
        },
        headers=auth_headers(officer_token),
    )
    po = client.post(
        "/procurement/purchase-orders",
        json={
            "supplier_id": supplier["supplier_id"],
            "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "25"}],
        },
        headers=auth_headers(officer_token),
    ).json()
    return officer_token, ingredient, po


def test_schedule_delivery_seeds_expected_quantities(client):
    """FR10.1."""
    officer_token, ingredient, po = _setup_po(client)
    resp = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "scheduled"


def test_confirm_receipt_within_threshold_updates_stock(client):
    """FR10.2 — within the deviation threshold, stock is updated directly."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery@restaurant.com", role="Delivery/Logistics Staff"
    )
    items_before = client.get(
        "/deliveries", headers=auth_headers(delivery_token)
    ).json()
    delivery_id = delivery["delivery_id"]

    # Fetch the delivery item id via a fresh receipt attempt — since there's
    # no dedicated "get delivery items" endpoint, use item_id=1 (first and
    # only DeliveryItem seeded from the single-line-item PO in a fresh DB).
    resp = client.post(
        f"/deliveries/{delivery_id}/confirm-receipt",
        json={"received_quantities": {"1": "24.500"}},  # within 10% of 25
        headers=auth_headers(delivery_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["delivery"]["status"] == "received"
    assert body["discrepancies"] == []

    ingredients = client.get("/inventory/ingredients", headers=auth_headers(delivery_token)).json()
    updated = next(i for i in ingredients if i["ingredient_id"] == ingredient["ingredient_id"])
    # started at 5, +24.5 received = 29.5
    assert updated["current_stock"] == "29.500"


def test_confirm_receipt_beyond_threshold_creates_discrepancy(client):
    """FR10.5 — routed to discrepancy flow instead of a standard receipt."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery2@restaurant.com", role="Delivery/Logistics Staff"
    )

    resp = client.post(
        f"/deliveries/{delivery['delivery_id']}/confirm-receipt",
        json={"received_quantities": {"1": "15.000"}},  # 40% short — well beyond threshold
        headers=auth_headers(delivery_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["discrepancies"]) == 1
    assert body["discrepancies"][0]["issue_type"] == "shortage"
    assert body["discrepancies"][0]["return_required"] is True


def test_confirm_receipt_rejects_negative_quantity(client):
    """FR10.5."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery3@restaurant.com", role="Delivery/Logistics Staff"
    )

    resp = client.post(
        f"/deliveries/{delivery['delivery_id']}/confirm-receipt",
        json={"received_quantities": {"1": "-5"}},
        headers=auth_headers(delivery_token),
    )
    assert resp.status_code == 422


def test_list_delivery_items_shows_what_confirm_receipt_needs(client):
    """FR10.2 — without this, there's no way to discover the item_id and
    expected_quantity confirm-receipt's {item_id: quantity} map needs."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()

    resp = client.get(f"/deliveries/{delivery['delivery_id']}/items", headers=auth_headers(officer_token))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["ingredient_id"] == ingredient["ingredient_id"]
    assert items[0]["expected_quantity"] == "25.000"
    assert items[0]["received_quantity"] is None
