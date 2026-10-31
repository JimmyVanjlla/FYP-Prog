"""FR10.1: the delivery calendar, which needs a date window and (since
Delivery/Logistics Staff can't read purchase orders) the supplier on each
row; plus the line items behind a PO."""
from tests.conftest import auth_headers, register_and_login
from tests.test_delivery import _setup_po


def _scheduled(client, day="2026-08-15"):
    officer_token, ingredient, po = _setup_po(client)
    delivery = client.post(
        "/deliveries",
        json={"po_id": po["po_id"], "scheduled_date": day},
        headers=auth_headers(officer_token),
    ).json()
    return officer_token, ingredient, po, delivery


def test_deliveries_can_be_listed_for_a_date_window(client):
    officer_token, _, _, delivery = _scheduled(client, "2026-08-15")
    headers = auth_headers(officer_token)

    inside = client.get(
        "/deliveries", params={"date_from": "2026-08-10", "date_to": "2026-08-20"}, headers=headers
    ).json()
    before = client.get("/deliveries", params={"date_to": "2026-08-14"}, headers=headers).json()
    after = client.get("/deliveries", params={"date_from": "2026-08-16"}, headers=headers).json()
    on_the_day = client.get(
        "/deliveries", params={"date_from": "2026-08-15", "date_to": "2026-08-15"}, headers=headers
    ).json()

    assert [d["delivery_id"] for d in inside] == [delivery["delivery_id"]]
    assert before == [] and after == []
    assert len(on_the_day) == 1  # the window is inclusive at both ends


def test_delivery_list_carries_supplier_and_value_for_staff_who_cannot_read_pos(client):
    _scheduled(client)
    delivery_staff = auth_headers(
        register_and_login(client, email="delivery@restaurant.com", role="Delivery/Logistics Staff")
    )

    # They really can't read purchase orders directly...
    assert client.get("/procurement/purchase-orders", headers=delivery_staff).status_code == 403
    # ...so the delivery row has to tell them who it's from.
    row = client.get("/deliveries", headers=delivery_staff).json()[0]
    assert row["supplier_name"] == "Fresh Farm Supplies"
    assert row["po_total_cost"] == "230.00"  # 25 kg x RM 9.20


def test_po_line_items_can_be_read(client):
    officer_token, ingredient, po, _ = _scheduled(client)

    items = client.get(f"/procurement/purchase-orders/{po['po_id']}/items", headers=auth_headers(officer_token)).json()

    assert len(items) == 1
    assert items[0]["ingredient_id"] == ingredient["ingredient_id"]
    assert items[0]["quantity"] == "25.000"
    assert items[0]["unit_price"] == "9.20"


def test_po_items_for_unknown_po_is_404_and_kitchen_staff_are_refused(client):
    officer_token, *_ = _scheduled(client)
    assert client.get("/procurement/purchase-orders/9999/items", headers=auth_headers(officer_token)).status_code == 404

    kitchen = auth_headers(register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff"))
    assert client.get("/procurement/purchase-orders/1/items", headers=kitchen).status_code == 403
