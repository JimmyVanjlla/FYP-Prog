"""Pagination coverage for the list endpoints that previously returned an
entire table unbounded (see the "Real gaps" audit that added limit/offset
across menu, inventory, forecasting, kitchen, waste, feedback, staffing,
procurement, and delivery). These two endpoints stand in for the pattern,
which is identical everywhere else it was applied."""
from tests.conftest import auth_headers, register_and_login


def test_orders_list_respects_limit_and_offset(client):
    manager_token = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    headers = auth_headers(manager_token)
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"},
        headers=headers,
    ).json()

    for day in range(1, 11):  # 10 orders, distinct dates for a stable sort
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": day,
                "meal_period": "Lunch",
                "order_date": f"2026-01-{day:02d}",
            },
            headers=headers,
        )

    first_page = client.get("/forecasting/orders", params={"limit": 4, "offset": 0}, headers=headers)
    assert first_page.status_code == 200
    assert len(first_page.json()) == 4

    second_page = client.get("/forecasting/orders", params={"limit": 4, "offset": 4}, headers=headers)
    assert len(second_page.json()) == 4

    # No overlap between pages (order_date desc, so page 1 is the most
    # recent 4 dates and page 2 is the next 4).
    first_ids = {o["order_id"] for o in first_page.json()}
    second_ids = {o["order_id"] for o in second_page.json()}
    assert first_ids.isdisjoint(second_ids)

    everything = client.get("/forecasting/orders", params={"limit": 500}, headers=headers)
    assert len(everything.json()) == 10


def test_pagination_limit_is_bounded(client):
    """limit is capped (le=500) rather than accepting an unbounded value
    that would defeat the point of pagination."""
    manager_token = register_and_login(client, email="manager2@restaurant.com", role="Restaurant Manager")
    headers = auth_headers(manager_token)
    resp = client.get("/forecasting/orders", params={"limit": 10_000}, headers=headers)
    assert resp.status_code == 422


def test_menu_items_list_respects_limit(client):
    manager_token = register_and_login(client, email="manager3@restaurant.com", role="Restaurant Manager")
    headers = auth_headers(manager_token)
    for i in range(5):
        client.post(
            "/menu-items",
            json={"name": f"Dish {i}", "price": "5.00", "category": "Rice"},
            headers=headers,
        )
    resp = client.get("/menu-items", params={"limit": 2}, headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2
