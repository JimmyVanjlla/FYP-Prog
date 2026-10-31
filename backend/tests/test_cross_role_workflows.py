"""Integration tests across roles (Form 2: "Full system integration tested for
all user roles"). Each test follows one real workflow through the API with
the different people who'd actually be involved, rather than testing one
endpoint at a time: it's the handoffs between roles that these exist for.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.models.forecasting import Forecast
from tests.conftest import auth_headers, register_and_login

TOMORROW = date.today() + timedelta(days=1)


def _who(client, role, email):
    return auth_headers(register_and_login(client, email=email, role=role))


def _notifications(client, headers, type_):
    return [n for n in client.get("/kitchen/notifications", headers=headers).json() if n["type"] == type_]


def test_ingredients_flow_from_purchase_order_to_stock(client):
    """Procurement Officer raises a PO -> Manager approves -> Officer
    schedules the delivery -> Delivery staff confirm what arrived -> Inventory
    Staff verify it into stock. Stock must only change at the last step."""
    manager = _who(client, "Restaurant Manager", "manager@restaurant.com")
    officer = _who(client, "Procurement Officer", "officer@restaurant.com")
    inventory = _who(client, "Inventory Staff", "inventory@restaurant.com")
    delivery = _who(client, "Delivery/Logistics Staff", "delivery@restaurant.com")

    supplier = client.post(
        "/procurement/suppliers", json={"name": "Fresh Farm", "contact_info": "+60 12-345 6789"}, headers=officer
    ).json()
    chicken = client.post(
        "/inventory/ingredients", json={"name": "Chicken", "unit": "kg", "current_stock": "5"}, headers=inventory
    ).json()
    client.post(
        "/procurement/suppliers/pricing",
        json={"supplier_id": supplier["supplier_id"], "ingredient_id": chicken["ingredient_id"], "unit_price": "12.00"},
        headers=officer,
    )
    client.post(
        "/procurement/budget",
        json={"month": date.today().replace(day=1).isoformat(), "budget_limit": "2000.00"},
        headers=manager,
    )

    po = client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": chicken["ingredient_id"], "quantity": "20"}]},
        headers=officer,
    ).json()
    assert po["status"] == "pending_approval"
    assert po["total_cost"] == "240.00"

    # The Manager sees it in their approval queue and approves it...
    queue = client.get("/procurement/purchase-orders", params={"status_filter": "pending_approval"}, headers=manager).json()
    assert [p["po_id"] for p in queue] == [po["po_id"]]
    assert client.post(f"/procurement/purchase-orders/{po['po_id']}/approve", headers=manager).json()["status"] == "approved"
    # ...and the Officer who raised it is told.
    assert len(_notifications(client, officer, "po_approved")) == 1

    sched = client.post(
        "/deliveries", json={"po_id": po["po_id"], "scheduled_date": TOMORROW.isoformat()}, headers=officer
    ).json()
    item = client.get(f"/deliveries/{sched['delivery_id']}/items", headers=delivery).json()[0]

    received = client.post(
        f"/deliveries/{sched['delivery_id']}/confirm-receipt",
        json={"received_quantities": {str(item["item_id"]): "20"}},
        headers=delivery,
    ).json()
    assert received["delivery"]["status"] == "delivered"
    # Receipt is not stock: still waiting on the Inventory Staff check.
    stock = lambda: next(  # noqa: E731
        Decimal(i["current_stock"]) for i in client.get("/inventory/ingredients", headers=inventory).json()
    )
    assert stock() == Decimal("5")

    # Delivery staff can't verify into stock; Inventory Staff can.
    assert client.post(f"/deliveries/{sched['delivery_id']}/verify", headers=delivery).status_code == 403
    assert client.post(f"/deliveries/{sched['delivery_id']}/verify", headers=inventory).status_code == 200
    assert stock() == Decimal("25")

    # The PO followed the delivery through the shared lifecycle, and the
    # month's budget reflects the spend.
    assert client.get("/procurement/purchase-orders", headers=manager).json()[0]["status"] == "delivered"
    budget = client.get("/procurement/budget/utilisation", headers=manager).json()
    assert Decimal(budget["spent"]) == Decimal("240.00")
    assert Decimal(budget["remaining"]) == Decimal("1760.00")

    # Every actor's writes are in the audit trail (FR1.5).
    actions = [a["action"] for a in client.get("/users/audit-logs", params={"limit": 500}, headers=manager).json()]
    for expected in (
        "POST /procurement/purchase-orders",
        f"POST /procurement/purchase-orders/{po['po_id']}/approve",
        "POST /deliveries",
        f"POST /deliveries/{sched['delivery_id']}/confirm-receipt",
        f"POST /deliveries/{sched['delivery_id']}/verify",
    ):
        assert expected in actions


def test_a_short_delivery_blocks_stock_until_resolved(client):
    """A shortage routes to the discrepancy flow: Inventory Staff can't add
    it to stock until it's resolved, and the return has to be closed out."""
    manager = _who(client, "Restaurant Manager", "manager@restaurant.com")
    officer = _who(client, "Procurement Officer", "officer@restaurant.com")
    inventory = _who(client, "Inventory Staff", "inventory@restaurant.com")
    delivery = _who(client, "Delivery/Logistics Staff", "delivery@restaurant.com")

    supplier = client.post(
        "/procurement/suppliers", json={"name": "Pasar Besar", "contact_info": "x"}, headers=officer
    ).json()
    rice = client.post(
        "/inventory/ingredients", json={"name": "Rice", "unit": "kg", "current_stock": "0"}, headers=inventory
    ).json()
    client.post(
        "/procurement/suppliers/pricing",
        json={"supplier_id": supplier["supplier_id"], "ingredient_id": rice["ingredient_id"], "unit_price": "3.00"},
        headers=officer,
    )
    po = client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": rice["ingredient_id"], "quantity": "50"}]},
        headers=officer,
    ).json()
    client.post(f"/procurement/purchase-orders/{po['po_id']}/approve", headers=manager)
    sched = client.post(
        "/deliveries", json={"po_id": po["po_id"], "scheduled_date": TOMORROW.isoformat()}, headers=officer
    ).json()
    item = client.get(f"/deliveries/{sched['delivery_id']}/items", headers=delivery).json()[0]

    result = client.post(
        f"/deliveries/{sched['delivery_id']}/confirm-receipt",
        json={"received_quantities": {str(item["item_id"]): "30"}},  # 40% short
        headers=delivery,
    ).json()
    assert result["delivery"]["status"] == "return_pending"
    discrepancy = result["discrepancies"][0]

    # Nothing is added to stock for a delivery in dispute.
    assert client.post(f"/deliveries/{sched['delivery_id']}/verify", headers=inventory).status_code == 409
    # The return can't be closed while the discrepancy is open...
    status_url = f"/deliveries/{sched['delivery_id']}/status"
    assert client.patch(status_url, json={"status": "return_resolved"}, headers=delivery).status_code == 409
    # ...but can once the Officer has resolved it with the supplier.
    assert client.post(f"/deliveries/discrepancies/{discrepancy['discrepancy_id']}/resolve", headers=officer).status_code == 200
    assert client.patch(status_url, json={"status": "return_resolved"}, headers=delivery).json()["status"] == "return_resolved"


def test_kitchen_leftovers_drive_a_portion_change_the_manager_approves(client, db_session):
    """The system's central feedback loop, across Kitchen Staff and the
    Manager: prep from a forecast -> leftovers logged -> a dish flagged ->
    Manager approves a smaller portion -> the recipe itself changes."""
    manager = _who(client, "Restaurant Manager", "manager@restaurant.com")
    kitchen = _who(client, "Kitchen Staff", "kitchen@restaurant.com")
    inventory = _who(client, "Inventory Staff", "inventory@restaurant.com")

    rice = client.post(
        "/inventory/ingredients", json={"name": "Rice", "unit": "kg", "current_stock": "100"}, headers=inventory
    ).json()
    dish = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager
    ).json()
    client.post(
        f"/menu-items/{dish['menu_item_id']}/recipe-links",
        json={"ingredient_id": rice["ingredient_id"], "quantity_per_serving": "0.200"},
        headers=manager,
    )
    db_session.add(
        Forecast(
            menu_item_id=dish["menu_item_id"], meal_period="Lunch", forecast_date=TOMORROW, predicted_quantity=Decimal("40.00")
        )
    )
    db_session.commit()

    # Kitchen Staff get the recommendation; a large change needs a reason.
    rec = client.post(
        "/kitchen/prep-recommendations",
        json={"menu_item_id": dish["menu_item_id"], "meal_period": "Lunch", "forecast_date": TOMORROW.isoformat()},
        headers=kitchen,
    ).json()
    confirm = f"/kitchen/prep-recommendations/{rec['recommendation_id']}/confirm"
    assert client.post(confirm, json={"confirmed_quantity": "60"}, headers=kitchen).status_code == 422
    assert client.post(
        confirm, json={"confirmed_quantity": "60", "deviation_reason": "Large booking"}, headers=kitchen
    ).status_code == 201

    # A week of heavy leftovers (40% of what was prepared).
    for days_ago in range(1, 6):
        client.post(
            "/kitchen/leftover-logs",
            json={
                "menu_item_id": dish["menu_item_id"],
                "service_period_date": (date.today() - timedelta(days=days_ago)).isoformat(),
                "prepared_quantity": "10",
                "leftover_quantity": "4",
                "leftover_level": "Mostly Uneaten",
            },
            headers=kitchen,
        )
    # ...which also becomes waste the Manager can see.
    assert client.get("/waste/logs", headers=manager).json()

    # The Manager runs the analysis, sees the flag, and approves the cut.
    assert client.post("/portion-feedback/analyze", headers=manager).json()["flagged_count"] == 1
    pending = client.get(
        "/portion-feedback/recommendations", params={"status_filter": "pending"}, headers=manager
    ).json()
    assert [p["menu_item_id"] for p in pending] == [dish["menu_item_id"]]
    assert client.post(
        f"/portion-feedback/recommendations/{pending[0]['recommendation_id']}/approve", headers=manager
    ).status_code == 200

    # The approval changed the recipe, not just the recommendation's status.
    item = next(m for m in client.get("/menu-items", headers=manager).json() if m["menu_item_id"] == dish["menu_item_id"])
    assert Decimal(item["recipe_links"][0]["quantity_per_serving"]) < Decimal("0.200")


def test_shift_from_schedule_to_closing_report(client, db_session):
    """Shift Supervisor builds a roster from the recommendation, publishes it,
    staff see it and are notified, attendance is taken, and the shift is closed
    against the forecast."""
    manager = _who(client, "Restaurant Manager", "manager@restaurant.com")
    supervisor = _who(client, "Shift Supervisor", "supervisor@restaurant.com")
    cook = _who(client, "Kitchen Staff", "cook@restaurant.com")
    cook_id = client.get("/users/me", headers=cook).json()["user_id"]

    dish = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager
    ).json()
    db_session.add(
        Forecast(
            menu_item_id=dish["menu_item_id"], meal_period="Dinner", forecast_date=TOMORROW, predicted_quantity=Decimal("120.00")
        )
    )
    db_session.commit()

    schedule = client.post(
        "/staffing/schedules", json={"date": TOMORROW.isoformat(), "meal_period": "Dinner"}, headers=supervisor
    ).json()
    sid = schedule["schedule_id"]
    recs = client.post(f"/staffing/schedules/{sid}/recommendations", headers=supervisor).json()
    assert {r["station"]: r["recommended_staff_count"] for r in recs} == {"Kitchen": 2, "Front of House": 2}

    # The supervisor can find the cook to assign; the cook can't assign themselves.
    assert cook_id in {s["user_id"] for s in client.get("/staffing/staff", headers=supervisor).json()}
    assert client.post(
        f"/staffing/schedules/{sid}/assignments", json={"staff_id": cook_id, "station": "Kitchen"}, headers=cook
    ).status_code == 403
    assignment = client.post(
        f"/staffing/schedules/{sid}/assignments", json={"staff_id": cook_id, "station": "Kitchen"}, headers=supervisor
    ).json()
    # No double-booking on the same shift.
    assert client.post(
        f"/staffing/schedules/{sid}/assignments", json={"staff_id": cook_id, "station": "Front of House"}, headers=supervisor
    ).status_code == 409

    # Before publishing the cook sees nothing; after, the shift and a notification.
    assert client.get("/staffing/my-schedule", headers=cook).json() == []
    client.post(f"/staffing/schedules/{sid}/publish", headers=supervisor)
    mine = client.get("/staffing/my-schedule", headers=cook).json()
    assert [(m["date"], m["meal_period"], m["station"]) for m in mine] == [(TOMORROW.isoformat(), "Dinner", "Kitchen")]
    assert len(_notifications(client, cook, "shift_published")) == 1

    # Opening (attendance) and closing against the forecast.
    client.patch(
        f"/staffing/assignments/{assignment['assignment_id']}/attendance",
        json={"attendance_status": "confirmed"},
        headers=supervisor,
    )
    assert client.get("/staffing/my-schedule", headers=cook).json()[0]["attendance_status"] == "confirmed"
    closing = client.post(
        f"/staffing/schedules/{sid}/closing-report", json={"actual_order_volume": 130}, headers=supervisor
    ).json()
    assert closing["forecasted_volume"] == 120
    assert closing["variance"] == 10

    # Publishing with only 1 of the 2 recommended in the kitchen was logged.
    log = [a["action"] for a in client.get("/users/audit-logs", params={"limit": 500}, headers=manager).json()]
    assert any(a.startswith(f"staffing_deviation:schedule={sid}:station=Kitchen") for a in log)


def test_roles_are_confined_to_their_own_work(client):
    """The same boundary from the other side: each role is refused the other
    roles' actions, however it's phrased."""
    kitchen = _who(client, "Kitchen Staff", "kitchen@restaurant.com")
    delivery = _who(client, "Delivery/Logistics Staff", "delivery@restaurant.com")
    officer = _who(client, "Procurement Officer", "officer@restaurant.com")
    supervisor = _who(client, "Shift Supervisor", "supervisor@restaurant.com")

    forbidden = [
        ("kitchen creating a menu item", client.post("/menu-items", json={"name": "x", "price": "1", "category": "x"}, headers=kitchen)),
        ("kitchen reading the audit trail", client.get("/users/audit-logs", headers=kitchen)),
        ("kitchen approving a purchase order", client.post("/procurement/purchase-orders/1/approve", headers=kitchen)),
        ("delivery staff changing settings", client.patch("/config", json={"leftover_rate_threshold": "5"}, headers=delivery)),
        ("delivery staff creating accounts", client.post("/users", json={"name": "n", "email": "n@x.com", "password": "password123", "role": "Kitchen Staff"}, headers=delivery)),
        ("procurement logging leftovers", client.post("/kitchen/leftover-logs", json={"menu_item_id": 1, "service_period_date": "2026-01-01", "prepared_quantity": "1", "leftover_quantity": "0", "leftover_level": "x"}, headers=officer)),
        ("procurement reading reports", client.get("/reports", headers=officer)),
        ("supervisor adjusting stock", client.post("/inventory/stock-adjustments", json={"ingredient_id": 1, "adjusted_quantity": "1", "reason_category": "miscount"}, headers=supervisor)),
        ("supervisor generating reports", client.post("/reports/weekly", json={"period_start": "2026-01-01", "period_end": "2026-01-07"}, headers=supervisor)),
    ]
    for label, response in forbidden:
        assert response.status_code == 403, f"{label} was not refused ({response.status_code})"
