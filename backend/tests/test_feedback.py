from datetime import date, timedelta
from decimal import Decimal

from app.models.kitchen import LeftoverLog
from tests.conftest import auth_headers, register_and_login


def _manager_token(client):
    return register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")


def _seed_leftover_logs(db_session, *, menu_item_id: int, staff_id: int, leftover_rate_pct: float):
    """Seeds enough LeftoverLog rows (within the default 14-day analysis
    window) to produce the given leftover rate."""
    prepared = Decimal("100")
    leftover = prepared * Decimal(str(leftover_rate_pct)) / 100
    log = LeftoverLog(
        menu_item_id=menu_item_id,
        service_period_date=date.today() - timedelta(days=1),
        prepared_quantity=prepared,
        leftover_quantity=leftover,
        leftover_level="Mostly Uneaten",
        staff_id=staff_id,
    )
    db_session.add(log)
    db_session.commit()


def test_high_leftover_dish_is_flagged(client, db_session):
    """FR7.1 — default leftover_rate_threshold is 15%."""
    manager_token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(manager_token),
    ).json()
    kitchen_token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    kitchen_user_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]

    _seed_leftover_logs(
        db_session, menu_item_id=item["menu_item_id"], staff_id=kitchen_user_id, leftover_rate_pct=30
    )

    resp = client.post("/portion-feedback/analyze", headers=auth_headers(manager_token))
    assert resp.status_code == 200
    assert resp.json()["flagged_count"] == 1

    recommendations = client.get("/portion-feedback/recommendations", headers=auth_headers(manager_token)).json()
    assert len(recommendations) == 1
    assert recommendations[0]["status"] == "pending"
    assert float(recommendations[0]["leftover_rate"]) == 30.0


def test_low_leftover_dish_is_not_flagged(client, db_session):
    manager_token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Roti Canai", "price": "3.00", "category": "Side"},
        headers=auth_headers(manager_token),
    ).json()
    kitchen_token = register_and_login(client, email="kitchen2@restaurant.com", role="Kitchen Staff")
    kitchen_user_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]

    _seed_leftover_logs(
        db_session, menu_item_id=item["menu_item_id"], staff_id=kitchen_user_id, leftover_rate_pct=5
    )

    resp = client.post("/portion-feedback/analyze", headers=auth_headers(manager_token))
    assert resp.json()["flagged_count"] == 0


def test_approving_recommendation_shrinks_recipe_portions(client, db_session):
    """FR7.2 / FR7.3 — approval scales every linked ingredient's
    quantity_per_serving down by the reduction factor."""
    manager_token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(manager_token),
    ).json()
    inv_token = register_and_login(client, email="inv@restaurant.com", role="Inventory Staff")
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Rice", "unit": "kg", "current_stock": "50"},
        headers=auth_headers(inv_token),
    ).json()
    client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity_per_serving": "0.200"},
        headers=auth_headers(manager_token),
    )

    kitchen_token = register_and_login(client, email="kitchen3@restaurant.com", role="Kitchen Staff")
    kitchen_user_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]
    _seed_leftover_logs(
        db_session, menu_item_id=item["menu_item_id"], staff_id=kitchen_user_id, leftover_rate_pct=40
    )
    client.post("/portion-feedback/analyze", headers=auth_headers(manager_token))
    reco = client.get("/portion-feedback/recommendations", headers=auth_headers(manager_token)).json()[0]

    resp = client.post(
        f"/portion-feedback/recommendations/{reco['recommendation_id']}/approve",
        headers=auth_headers(manager_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    updated_item = client.get("/menu-items", headers=auth_headers(manager_token)).json()
    updated = next(m for m in updated_item if m["menu_item_id"] == item["menu_item_id"])
    # 0.200 * 0.90 = 0.180
    assert updated["recipe_links"][0]["quantity_per_serving"] == "0.180"
