from datetime import date

from tests.conftest import auth_headers, register_and_login


def _officer_token(client):
    return register_and_login(client, email="officer@restaurant.com", role="Procurement Officer")


def _manager_token(client):
    return register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")


def _create_supplier_and_ingredient(client, officer_token, manager_token=None):
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
        json={"supplier_id": supplier["supplier_id"], "ingredient_id": ingredient["ingredient_id"], "unit_price": "9.20"},
        headers=auth_headers(officer_token),
    )
    return supplier, ingredient


def test_create_supplier_and_pricing(client):
    """FR9.1."""
    officer_token = _officer_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)
    assert supplier["name"] == "Fresh Farm Supplies"


def test_purchase_order_computes_total_from_pricing(client):
    """FR9.3 — line item cost pulled from SupplierPricing."""
    officer_token = _officer_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)

    resp = client.post(
        "/procurement/purchase-orders",
        json={
            "supplier_id": supplier["supplier_id"],
            "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "25"}],
        },
        headers=auth_headers(officer_token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total_cost"] == "230.00"  # 25 * 9.20
    assert body["status"] == "pending_approval"


def test_purchase_order_rejects_zero_quantity(client):
    """FR9.6."""
    officer_token = _officer_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)

    resp = client.post(
        "/procurement/purchase-orders",
        json={
            "supplier_id": supplier["supplier_id"],
            "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "0"}],
        },
        headers=auth_headers(officer_token),
    )
    assert resp.status_code == 422


def test_purchase_order_over_budget_warns_not_blocks(client):
    """FR9.6 — a warning field, not a rejection."""
    officer_token = _officer_token(client)
    manager_token = _manager_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)

    # Budget checks are always against the real current month (a PO's
    # created_at is "now"), so the test has to set the budget for that
    # same month rather than a hardcoded one.
    current_month = date.today().replace(day=1).isoformat()
    client.post(
        "/procurement/budget",
        json={"month": current_month, "budget_limit": "100.00"},
        headers=auth_headers(manager_token),
    )

    resp = client.post(
        "/procurement/purchase-orders",
        json={
            "supplier_id": supplier["supplier_id"],
            "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "50"}],  # 460.00
        },
        headers=auth_headers(officer_token),
    )
    assert resp.status_code == 201  # not blocked
    assert resp.json()["exceeds_budget"] is True


def test_manager_can_approve_purchase_order(client):
    """FR9.3."""
    officer_token = _officer_token(client)
    manager_token = _manager_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)
    po = client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "5"}]},
        headers=auth_headers(officer_token),
    ).json()

    resp = client.post(f"/procurement/purchase-orders/{po['po_id']}/approve", headers=auth_headers(manager_token))
    assert resp.json()["status"] == "approved"


def test_flag_supplier_discrepancy(client):
    """FR9.5."""
    officer_token = _officer_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)
    po = client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "5"}]},
        headers=auth_headers(officer_token),
    ).json()

    resp = client.post(
        "/procurement/discrepancies",
        json={
            "po_id": po["po_id"],
            "supplier_id": supplier["supplier_id"],
            "description": "Invoice quantity did not match delivery note",
        },
        headers=auth_headers(officer_token),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "open"


def test_menu_profit_margin_uses_real_pricing(client):
    """FR2.1 — closing the Sprint 1 stub now that SupplierPricing exists."""
    officer_token = _officer_token(client)
    manager_token = _manager_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)

    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(manager_token),
    ).json()
    client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity_per_serving": "0.200"},
        headers=auth_headers(manager_token),
    )

    updated = client.get("/menu-items", headers=auth_headers(manager_token)).json()
    dish = next(m for m in updated if m["menu_item_id"] == item["menu_item_id"])
    # 12.50 - (0.200 * 9.20) = 12.50 - 1.84 = 10.66
    assert dish["profit_margin"] == "10.66"


def test_list_supplier_pricing(client):
    """FR9.1 — "supplier directory with pricing" implies being able to
    see it, not just set it."""
    officer_token = _officer_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)

    resp = client.get("/procurement/suppliers/pricing", headers=auth_headers(officer_token))
    assert resp.status_code == 200
    pricing = resp.json()
    assert len(pricing) == 1
    assert pricing[0]["supplier_id"] == supplier["supplier_id"]
    assert pricing[0]["unit_price"] == "9.20"


def test_list_budgets(client):
    """FR9.4 — "track monthly procurement budget configuration" needs a
    way to see what's been configured."""
    manager_token = _manager_token(client)
    client.post(
        "/procurement/budget",
        json={"month": "2026-08-01", "budget_limit": "5000.00"},
        headers=auth_headers(manager_token),
    )

    resp = client.get("/procurement/budget", headers=auth_headers(manager_token))
    assert resp.status_code == 200
    budgets = resp.json()
    assert any(b["budget_limit"] == "5000.00" for b in budgets)


def test_deactivate_supplier(client):
    """UC-PS-04 Alt Flow 3a — "retains historical purchase order records...
    but excludes it from future recommendations.\""""
    officer_token = _officer_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)

    resp = client.patch(
        f"/procurement/suppliers/{supplier['supplier_id']}/deactivate", headers=auth_headers(officer_token)
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Excluded from future pricing lookups (get_unit_price filters to
    # active suppliers) — falls back to 0.00 with no active supplier left.
    po = client.post(
        "/procurement/purchase-orders",
        json={
            "supplier_id": supplier["supplier_id"],
            "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "5"}],
        },
        headers=auth_headers(officer_token),
    ).json()
    assert po["total_cost"] == "0.00"


def test_resolve_supplier_discrepancy(client):
    """UC-PS-07 Alt Flow 3a."""
    officer_token = _officer_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)
    po = client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "5"}]},
        headers=auth_headers(officer_token),
    ).json()
    discrepancy = client.post(
        "/procurement/discrepancies",
        json={"po_id": po["po_id"], "supplier_id": supplier["supplier_id"], "description": "Short delivery"},
        headers=auth_headers(officer_token),
    ).json()

    resp = client.post(
        f"/procurement/discrepancies/{discrepancy['discrepancy_id']}/resolve", headers=auth_headers(officer_token)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


def test_budget_utilisation_view(client):
    """UC-PS-06 "View Monthly Budget Utilisation"."""
    from datetime import date

    officer_token = _officer_token(client)
    manager_token = _manager_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)

    current_month = date.today().replace(day=1).isoformat()
    client.post(
        "/procurement/budget",
        json={"month": current_month, "budget_limit": "1000.00"},
        headers=auth_headers(manager_token),
    )
    client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "5"}]},
        headers=auth_headers(officer_token),
    )

    resp = client.get("/procurement/budget/utilisation", headers=auth_headers(officer_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["budget_limit"] == "1000.00"
    assert body["spent"] == "46.00"  # 5 * 9.20
    assert body["remaining"] == "954.00"
    assert body["utilisation_pct"] == "4.60"


def test_po_approve_notifies_procurement_officer(client):
    """UC-PS-01 main flow step 5."""
    officer_token = _officer_token(client)
    manager_token = _manager_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)
    po = client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "5"}]},
        headers=auth_headers(officer_token),
    ).json()

    client.post(f"/procurement/purchase-orders/{po['po_id']}/approve", headers=auth_headers(manager_token))

    notifications = client.get("/kitchen/notifications", headers=auth_headers(officer_token)).json()
    assert any(n["type"] == "po_approved" for n in notifications)


def test_po_reject_notifies_procurement_officer(client):
    """UC-PS-01 Alt Flow 4a."""
    officer_token = _officer_token(client)
    manager_token = _manager_token(client)
    supplier, ingredient = _create_supplier_and_ingredient(client, officer_token)
    po = client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": ingredient["ingredient_id"], "quantity": "5"}]},
        headers=auth_headers(officer_token),
    ).json()

    client.post(f"/procurement/purchase-orders/{po['po_id']}/reject", headers=auth_headers(manager_token))

    notifications = client.get("/kitchen/notifications", headers=auth_headers(officer_token)).json()
    assert any(n["type"] == "po_rejected" for n in notifications)
