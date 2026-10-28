"""
Continuation of seed_dev_data.py after it timed out on /forecasting/train
(Prophet training 12 items x 2 meal periods sequentially took longer than
the default 30s HTTP timeout). Everything up to order/leftover-log seeding
already succeeded and is in the DB; this picks up from forecast training
through the procurement/delivery cycle and weekly report, re-fetching IDs
from the API rather than recreating anything.
"""
from __future__ import annotations

from datetime import date, timedelta

import httpx

BASE_URL = "http://127.0.0.1:8000"
PASSWORD = "Password123!"

ACCOUNTS = {
    "Restaurant Manager": "manager@test.com",
    "Kitchen Staff": "kitchen@test.com",
    "Inventory Staff": "inventory@test.com",
    "Procurement Officer": "procurement@test.com",
    "Delivery/Logistics Staff": "delivery@test.com",
}


def login(client: httpx.Client, email: str) -> str:
    resp = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    resp.raise_for_status()
    return resp.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=300)
    tokens = {role: login(client, email) for role, email in ACCOUNTS.items()}
    manager = auth(tokens["Restaurant Manager"])
    procurement = auth(tokens["Procurement Officer"])
    delivery_staff = auth(tokens["Delivery/Logistics Staff"])
    inventory_staff = auth(tokens["Inventory Staff"])

    today = date.today()

    print("== Training forecasts (Algorithm 1) — this can take a while ==")
    resp = client.post("/forecasting/train", headers=manager)
    resp.raise_for_status()
    print(f"  {resp.json()}")

    print("== Analyzing leftover rates for portion recommendations (Algorithm 2) ==")
    resp = client.post("/portion-feedback/analyze", headers=manager)
    resp.raise_for_status()
    print(f"  {resp.json()}")

    print("== Aggregating weekly waste reduction trends ==")
    leftover_start = today - timedelta(days=21)
    for week in range(3):
        period_start = leftover_start + timedelta(days=week * 7)
        period_end = period_start + timedelta(days=6)
        resp = client.post(
            "/waste/trends",
            json={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
            headers=manager,
        )
        print(f"  {period_start} -> {period_end}: {resp.status_code}")

    print("== Fetching created entities ==")
    ingredients = {i["name"]: i["ingredient_id"] for i in client.get("/inventory/ingredients", headers=manager).json()}
    suppliers = {s["name"]: s["supplier_id"] for s in client.get("/procurement/suppliers", headers=manager).json()}
    print(f"  {len(ingredients)} ingredients, {len(suppliers)} suppliers")

    print("== Creating a procurement + delivery cycle ==")
    po1 = client.post(
        "/procurement/purchase-orders",
        json={
            "supplier_id": suppliers["Fresh Farm Poultry & Seafood"],
            "line_items": [
                {"ingredient_id": ingredients["Chicken"], "quantity": "20"},
                {"ingredient_id": ingredients["Prawns"], "quantity": "10"},
            ],
        },
        headers=procurement,
    )
    po1.raise_for_status()
    print(f"  PO #{po1.json()['po_id']} left pending_approval")

    po2 = client.post(
        "/procurement/purchase-orders",
        json={
            "supplier_id": suppliers["Pasar Besar Trading"],
            "line_items": [
                {"ingredient_id": ingredients["Rice"], "quantity": "30"},
                {"ingredient_id": ingredients["Cooking Oil"], "quantity": "15"},
            ],
        },
        headers=procurement,
    )
    po2.raise_for_status()
    po2_id = po2.json()["po_id"]
    client.post(f"/procurement/purchase-orders/{po2_id}/approve", headers=manager).raise_for_status()

    delivery = client.post(
        "/deliveries",
        json={"po_id": po2_id, "scheduled_date": today.isoformat()},
        headers=procurement,
    )
    delivery.raise_for_status()
    delivery_id = delivery.json()["delivery_id"]
    items = client.get(f"/deliveries/{delivery_id}/items", headers=delivery_staff).json()
    received = {str(i["item_id"]): str(i["expected_quantity"]) for i in items}
    client.post(
        f"/deliveries/{delivery_id}/confirm-receipt",
        json={"received_quantities": received},
        headers=delivery_staff,
    ).raise_for_status()
    client.post(f"/deliveries/{delivery_id}/verify", headers=inventory_staff).raise_for_status()
    print(f"  PO #{po2_id} approved, delivered, and verified (stock updated)")

    print("== Generating a weekly report ==")
    report = client.post(
        "/reporting/weekly",
        json={
            "period_start": (today - timedelta(days=7)).isoformat(),
            "period_end": today.isoformat(),
        },
        headers=manager,
    )
    print(f"  {report.status_code}: {report.json() if report.status_code < 300 else report.text}")

    print("\nDone.")


if __name__ == "__main__":
    main()
