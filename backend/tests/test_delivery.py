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
    assert resp.json()["status"] == "awaiting_delivery"

    # UC-PS-05 — the PO's own status tracks the same lifecycle.
    updated_po = client.get("/procurement/purchase-orders", headers=auth_headers(officer_token)).json()
    assert updated_po[0]["status"] == "awaiting_delivery"


def test_confirm_receipt_within_threshold_does_not_update_stock_yet(client):
    """UC-DM-02/UC-IM-01 — confirm-receipt (Delivery/Logistics Staff)
    records what arrived and moves status to "delivered", but does NOT
    touch Ingredient.current_stock; that's a separate Inventory Staff
    step (verify_delivery, checked in the next test)."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery@restaurant.com", role="Delivery/Logistics Staff"
    )
    delivery_id = delivery["delivery_id"]

    resp = client.post(
        f"/deliveries/{delivery_id}/confirm-receipt",
        json={"received_quantities": {"1": "24.500"}},  # within 10% of 25
        headers=auth_headers(delivery_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["delivery"]["status"] == "delivered"
    assert body["delivery"]["verified_by"] is None
    assert body["discrepancies"] == []

    ingredients = client.get("/inventory/ingredients", headers=auth_headers(delivery_token)).json()
    updated = next(i for i in ingredients if i["ingredient_id"] == ingredient["ingredient_id"])
    assert updated["current_stock"] == "5.000"  # unchanged — still just the starting stock

    updated_po = client.get("/procurement/purchase-orders", headers=auth_headers(officer_token)).json()
    assert updated_po[0]["status"] == "delivered"


def test_verify_delivery_then_updates_stock(client):
    """UC-IM-01 — Inventory Staff's separate verification step is what
    actually updates stock."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery1b@restaurant.com", role="Delivery/Logistics Staff"
    )
    client.post(
        f"/deliveries/{delivery['delivery_id']}/confirm-receipt",
        json={"received_quantities": {"1": "24.500"}},
        headers=auth_headers(delivery_token),
    )

    inv_token = register_and_login(client, email="inv_verify@restaurant.com", role="Inventory Staff")
    resp = client.post(f"/deliveries/{delivery['delivery_id']}/verify", headers=auth_headers(inv_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified_by"] is not None
    assert body["verified_at"] is not None

    ingredients = client.get("/inventory/ingredients", headers=auth_headers(inv_token)).json()
    updated = next(i for i in ingredients if i["ingredient_id"] == ingredient["ingredient_id"])
    # started at 5, +24.5 verified = 29.5
    assert updated["current_stock"] == "29.500"


def test_verify_delivery_blocked_while_discrepancy_open(client):
    """UC-IM-01 Alt Flow 3a — verification is blocked until the linked
    discrepancy is resolved, so incorrect quantities never get added to
    inventory."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery2@restaurant.com", role="Delivery/Logistics Staff"
    )
    client.post(
        f"/deliveries/{delivery['delivery_id']}/confirm-receipt",
        json={"received_quantities": {"1": "15.000"}},  # 40% short — beyond threshold
        headers=auth_headers(delivery_token),
    )

    inv_token = register_and_login(client, email="inv_verify2@restaurant.com", role="Inventory Staff")
    resp = client.post(f"/deliveries/{delivery['delivery_id']}/verify", headers=auth_headers(inv_token))
    assert resp.status_code == 409

    ingredients = client.get("/inventory/ingredients", headers=auth_headers(inv_token)).json()
    updated = next(i for i in ingredients if i["ingredient_id"] == ingredient["ingredient_id"])
    assert updated["current_stock"] == "5.000"  # still untouched


def test_confirm_receipt_beyond_threshold_creates_discrepancy_and_return_pending(client):
    """FR10.5 / UC-DM-03 Alt Flow 3a — a shortage requires a return, which
    routes the delivery straight to "return_pending"."""
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
        json={"received_quantities": {"1": "15.000"}},  # 40% short — well beyond threshold
        headers=auth_headers(delivery_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["discrepancies"]) == 1
    assert body["discrepancies"][0]["issue_type"] == "shortage"
    assert body["discrepancies"][0]["return_required"] is True
    assert body["delivery"]["status"] == "return_pending"


def test_confirm_receipt_rejects_negative_quantity(client):
    """FR10.5."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery4@restaurant.com", role="Delivery/Logistics Staff"
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


def test_update_delivery_status_pre_receipt_tracking(client):
    """UC-DM-04 — manual progression through pre-receipt tracking states."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery5@restaurant.com", role="Delivery/Logistics Staff"
    )

    resp = client.patch(
        f"/deliveries/{delivery['delivery_id']}/status",
        json={"status": "in_transit"},
        headers=auth_headers(delivery_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_transit"


def test_update_delivery_status_rejects_unsettable_value(client):
    """UC-DM-04 — "delivered"/"discrepancy_flagged" are decided by
    confirm-receipt's own comparison logic, not set directly."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery6@restaurant.com", role="Delivery/Logistics Staff"
    )

    resp = client.patch(
        f"/deliveries/{delivery['delivery_id']}/status",
        json={"status": "delivered"},
        headers=auth_headers(delivery_token),
    )
    assert resp.status_code == 422


def test_return_resolved_blocked_while_discrepancy_open(client):
    """UC-DM-04 Alt Flow 2a — "Return Resolved" is blocked until the
    discrepancy record is closed."""
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": "2026-08-15"},
        headers=auth_headers(officer_token),
    ).json()
    delivery_token = register_and_login(
        client, email="delivery7@restaurant.com", role="Delivery/Logistics Staff"
    )
    confirm = client.post(
        f"/deliveries/{delivery['delivery_id']}/confirm-receipt",
        json={"received_quantities": {"1": "15.000"}},  # triggers a discrepancy -> return_pending
        headers=auth_headers(delivery_token),
    ).json()

    blocked = client.patch(
        f"/deliveries/{delivery['delivery_id']}/status",
        json={"status": "return_resolved"},
        headers=auth_headers(delivery_token),
    )
    assert blocked.status_code == 409

    discrepancy_id = confirm["discrepancies"][0]["discrepancy_id"]
    client.post(f"/deliveries/discrepancies/{discrepancy_id}/resolve", headers=auth_headers(officer_token))

    allowed = client.patch(
        f"/deliveries/{delivery['delivery_id']}/status",
        json={"status": "return_resolved"},
        headers=auth_headers(delivery_token),
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "return_resolved"
