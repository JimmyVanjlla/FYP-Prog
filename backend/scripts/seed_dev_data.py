"""
Dev-only data seeder: populates a fresh database with a realistic Malaysian
restaurant's worth of data (menu, ingredients, suppliers, 8 weeks of order
history, leftover logs, a procurement/delivery cycle) so the app has
something to look at instead of empty screens.

Idempotent-ish: re-running it will fail on duplicate-email registration and
duplicate menu items/ingredients (name uniqueness isn't enforced at the DB
level, so re-running just adds a second copy of everything — intended for a
single run against a fresh database, not repeated seeding).

Usage (from backend/, with the venv active and the API server running):
    ./.venv/Scripts/python scripts/seed_dev_data.py
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

import httpx

BASE_URL = "http://127.0.0.1:8000"
PASSWORD = "Password123!"

ACCOUNTS = [
    ("Owner Account", "owner@test.com", "Restaurant Owner"),
    ("Manager Account", "manager@test.com", "Restaurant Manager"),
    ("Kitchen Account", "kitchen@test.com", "Kitchen Staff"),
    ("Inventory Account", "inventory@test.com", "Inventory Staff"),
    ("Supervisor Account", "supervisor@test.com", "Shift Supervisor"),
    ("Procurement Account", "procurement@test.com", "Procurement Officer"),
    ("Delivery Account", "delivery@test.com", "Delivery/Logistics Staff"),
]

# (name, unit, starting_stock, low_stock_threshold or None for system default)
INGREDIENTS = [
    ("Rice", "kg", "50", None),
    ("Chicken", "kg", "30", None),
    ("Egg", "pcs", "200", None),
    ("Cucumber", "kg", "10", None),
    ("Ikan Bilis", "kg", "8", None),
    ("Peanuts", "kg", "6", None),
    ("Sambal Chili", "kg", "10", None),
    ("Yellow Mee Noodles", "kg", "20", None),
    ("Kuey Teow Noodles", "kg", "20", None),
    ("Beansprouts", "kg", "9", "10"),  # deliberately under its own threshold -> Low stock
    ("Prawns", "kg", "12", None),
    ("Coconut Milk", "litre", "15", None),
    ("Tea Leaves", "kg", "3", None),
    ("Condensed Milk", "can", "40", None),
    ("Coffee Powder", "kg", "4", None),
    ("Milo Powder", "kg", "5", None),
    ("Flour", "kg", "25", None),
    ("Cooking Oil", "litre", "20", None),
    ("Curry Paste", "kg", "6", "8"),  # deliberately under its own threshold -> Low stock
]

# name -> supplier name (one supplier per ingredient keeps pricing simple)
SUPPLIERS = {
    "Pasar Besar Trading": ["Rice", "Flour", "Cooking Oil", "Sambal Chili", "Curry Paste"],
    "Fresh Farm Poultry & Seafood": ["Chicken", "Prawns", "Egg", "Cucumber"],
    "Kedai Runcit Supplies": [
        "Ikan Bilis", "Peanuts", "Yellow Mee Noodles", "Kuey Teow Noodles",
        "Beansprouts", "Coconut Milk", "Tea Leaves", "Condensed Milk",
        "Coffee Powder", "Milo Powder",
    ],
}

UNIT_PRICES = {
    "Rice": "3.20", "Flour": "2.80", "Cooking Oil": "6.50", "Sambal Chili": "9.00",
    "Curry Paste": "11.00", "Chicken": "12.50", "Prawns": "28.00", "Egg": "0.55",
    "Cucumber": "2.50", "Ikan Bilis": "22.00", "Peanuts": "14.00",
    "Yellow Mee Noodles": "4.50", "Kuey Teow Noodles": "4.80", "Beansprouts": "2.80",
    "Coconut Milk": "6.00", "Tea Leaves": "35.00", "Condensed Milk": "3.50",
    "Coffee Powder": "28.00", "Milo Powder": "18.00",
}

# name, category, price, [(ingredient, qty_per_serving), ...], avg_daily_demand
MENU_ITEMS = [
    ("Nasi Lemak", "Rice", "6.50", [
        ("Rice", "0.150"), ("Coconut Milk", "0.050"), ("Ikan Bilis", "0.020"),
        ("Peanuts", "0.010"), ("Egg", "1"), ("Sambal Chili", "0.030"),
    ], 38),
    ("Nasi Goreng Kampung", "Rice", "7.00", [
        ("Rice", "0.200"), ("Egg", "1"), ("Ikan Bilis", "0.020"),
        ("Sambal Chili", "0.020"), ("Cooking Oil", "0.020"),
    ], 22),
    ("Mee Goreng Mamak", "Noodles", "6.00", [
        ("Yellow Mee Noodles", "0.200"), ("Egg", "1"), ("Beansprouts", "0.050"),
        ("Cooking Oil", "0.020"), ("Sambal Chili", "0.020"),
    ], 26),
    ("Char Kuey Teow", "Noodles", "7.50", [
        ("Kuey Teow Noodles", "0.200"), ("Egg", "1"), ("Prawns", "0.080"),
        ("Beansprouts", "0.050"), ("Cooking Oil", "0.020"),
    ], 30),
    ("Roti Canai", "Bread", "2.20", [
        ("Flour", "0.100"), ("Cooking Oil", "0.010"),
    ], 45),
    ("Roti Telur", "Bread", "3.00", [
        ("Flour", "0.100"), ("Egg", "1"), ("Cooking Oil", "0.010"),
    ], 20),
    ("Chicken Rice", "Rice", "7.00", [
        ("Rice", "0.200"), ("Chicken", "0.150"), ("Cucumber", "0.030"),
    ], 34),
    ("Curry Laksa", "Noodles", "8.00", [
        ("Yellow Mee Noodles", "0.200"), ("Curry Paste", "0.080"),
        ("Coconut Milk", "0.100"), ("Chicken", "0.100"), ("Beansprouts", "0.030"),
    ], 18),
    ("Satay Ayam (5 sticks)", "Grill", "6.00", [
        ("Chicken", "0.150"), ("Peanuts", "0.020"),
    ], 15),
    ("Teh Tarik", "Beverage", "2.50", [
        ("Tea Leaves", "0.010"), ("Condensed Milk", "0.100"),
    ], 50),
    ("Kopi O", "Beverage", "2.00", [
        ("Coffee Powder", "0.015"),
    ], 28),
    ("Milo Ais", "Beverage", "3.00", [
        ("Milo Powder", "0.030"), ("Condensed Milk", "0.050"),
    ], 33),
]

# Menu items deliberately given a high leftover rate (> SystemConfig's 15%
# default threshold) so Algorithm 2 flags them and the Approvals screen has
# something real to show for "Portion size reviews".
HIGH_LEFTOVER_ITEMS = {"Curry Laksa", "Roti Telur"}

WEEKS_OF_ORDER_HISTORY = 8
LEFTOVER_LOG_DAYS = 21  # covers the 14-day feedback analysis window with margin


def register_and_login(client: httpx.Client, name: str, email: str, role: str) -> str:
    resp = client.post(
        "/auth/register",
        json={"name": name, "email": email, "password": PASSWORD, "role": role},
    )
    if resp.status_code not in (201, 400):
        resp.raise_for_status()
    login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    login.raise_for_status()
    return login.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=30)
    tokens: dict[str, str] = {}

    print("== Creating accounts ==")
    for name, email, role in ACCOUNTS:
        tokens[role] = register_and_login(client, name, email, role)
        print(f"  {role}: {email} / {PASSWORD}")

    manager = auth(tokens["Restaurant Manager"])
    kitchen = auth(tokens["Kitchen Staff"])
    inventory_staff = auth(tokens["Inventory Staff"])
    procurement = auth(tokens["Procurement Officer"])
    delivery_staff = auth(tokens["Delivery/Logistics Staff"])

    print("== Creating ingredients ==")
    ingredient_ids: dict[str, int] = {}
    for name, unit, stock, threshold in INGREDIENTS:
        payload = {"name": name, "unit": unit, "current_stock": stock}
        if threshold is not None:
            payload["low_stock_threshold"] = threshold
        resp = client.post("/inventory/ingredients", json=payload, headers=manager)
        resp.raise_for_status()
        ingredient_ids[name] = resp.json()["ingredient_id"]
    print(f"  {len(ingredient_ids)} ingredients created")

    print("== Creating suppliers + pricing ==")
    supplier_ids: dict[str, int] = {}
    for supplier_name, ingredient_names in SUPPLIERS.items():
        resp = client.post(
            "/procurement/suppliers",
            json={"name": supplier_name, "contact_info": f"+60 12-{random.randint(1000000, 9999999)}"},
            headers=procurement,
        )
        resp.raise_for_status()
        sid = resp.json()["supplier_id"]
        supplier_ids[supplier_name] = sid
        for ing_name in ingredient_names:
            client.post(
                "/procurement/suppliers/pricing",
                json={
                    "supplier_id": sid,
                    "ingredient_id": ingredient_ids[ing_name],
                    "unit_price": UNIT_PRICES[ing_name],
                },
                headers=procurement,
            ).raise_for_status()
    print(f"  {len(supplier_ids)} suppliers + pricing created")

    print("== Setting monthly budget ==")
    today = date.today()
    for month_offset in (0, -1):
        m = (today.replace(day=1) - timedelta(days=1)) if month_offset == -1 else today.replace(day=1)
        client.post(
            "/procurement/budget",
            json={"month": m.isoformat(), "budget_limit": "8000.00"},
            headers=manager,
        )

    print("== Creating menu items + recipe links ==")
    menu_item_ids: dict[str, int] = {}
    for name, category, price, recipe, _avg_demand in MENU_ITEMS:
        resp = client.post(
            "/menu-items",
            json={"name": name, "price": price, "category": category},
            headers=manager,
        )
        resp.raise_for_status()
        mid = resp.json()["menu_item_id"]
        menu_item_ids[name] = mid
        for ing_name, qty in recipe:
            client.post(
                f"/menu-items/{mid}/recipe-links",
                json={"ingredient_id": ingredient_ids[ing_name], "quantity_per_serving": qty},
                headers=manager,
            ).raise_for_status()
    print(f"  {len(menu_item_ids)} menu items + recipe links created")

    print(f"== Seeding {WEEKS_OF_ORDER_HISTORY} weeks of order history ==")
    start_date = today - timedelta(days=WEEKS_OF_ORDER_HISTORY * 7)
    order_count = 0
    for name, _category, _price, _recipe, avg_demand in MENU_ITEMS:
        mid = menu_item_ids[name]
        for day_offset in range(WEEKS_OF_ORDER_HISTORY * 7):
            d = start_date + timedelta(days=day_offset)
            weekend_boost = 1.3 if d.weekday() >= 5 else 1.0
            trend = 1.0 + 0.15 * (day_offset / (WEEKS_OF_ORDER_HISTORY * 7))  # gentle upward trend
            for meal_period, period_share in (("Lunch", 0.55), ("Dinner", 0.45)):
                mean = avg_demand * period_share * weekend_boost * trend
                qty = max(1, round(random.gauss(mean, mean * 0.15)))
                client.post(
                    "/forecasting/orders",
                    json={
                        "menu_item_id": mid,
                        "quantity": qty,
                        "meal_period": meal_period,
                        "order_date": d.isoformat(),
                    },
                    headers=manager,
                ).raise_for_status()
                order_count += 1
    print(f"  {order_count} order records created")

    print(f"== Seeding {LEFTOVER_LOG_DAYS} days of leftover logs ==")
    leftover_start = today - timedelta(days=LEFTOVER_LOG_DAYS)
    leftover_count = 0
    for name, _category, _price, _recipe, avg_demand in MENU_ITEMS:
        mid = menu_item_ids[name]
        high = name in HIGH_LEFTOVER_ITEMS
        for day_offset in range(LEFTOVER_LOG_DAYS):
            d = leftover_start + timedelta(days=day_offset)
            prepared = max(2, round(avg_demand * 0.5 * random.uniform(0.9, 1.1)))
            rate = random.uniform(0.25, 0.38) if high else random.uniform(0.03, 0.12)
            leftover = max(0, round(prepared * rate))
            level = "Mostly Uneaten" if rate > 0.2 else "Partially Eaten"
            client.post(
                "/kitchen/leftover-logs",
                json={
                    "menu_item_id": mid,
                    "service_period_date": d.isoformat(),
                    "prepared_quantity": prepared,
                    "leftover_quantity": leftover,
                    "leftover_level": level,
                },
                headers=kitchen,
            ).raise_for_status()
            leftover_count += 1
    print(f"  {leftover_count} leftover logs created (and their waste logs, automatically)")

    print("== Training forecasts (Algorithm 1) ==")
    resp = client.post("/forecasting/train", headers=manager)
    resp.raise_for_status()
    print(f"  {resp.json()}")

    print("== Analyzing leftover rates for portion recommendations (Algorithm 2) ==")
    resp = client.post("/portion-feedback/analyze", headers=manager)
    resp.raise_for_status()
    print(f"  {resp.json()}")

    print("== Aggregating weekly waste reduction trends ==")
    for week in range(LEFTOVER_LOG_DAYS // 7):
        period_start = leftover_start + timedelta(days=week * 7)
        period_end = period_start + timedelta(days=6)
        client.post(
            "/waste/trends",
            json={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
            headers=manager,
        )

    print("== Creating a procurement + delivery cycle ==")
    # PO #1: left pending, so the Manager's Approvals screen has something
    # real to approve/reject.
    po1 = client.post(
        "/procurement/purchase-orders",
        json={
            "supplier_id": supplier_ids["Fresh Farm Poultry & Seafood"],
            "line_items": [
                {"ingredient_id": ingredient_ids["Chicken"], "quantity": "20"},
                {"ingredient_id": ingredient_ids["Prawns"], "quantity": "10"},
            ],
        },
        headers=procurement,
    )
    po1.raise_for_status()
    print(f"  PO #{po1.json()['po_id']} left pending_approval")

    # PO #2: approved, scheduled, received, and verified end-to-end so
    # Inventory/Delivery data isn't empty either.
    po2 = client.post(
        "/procurement/purchase-orders",
        json={
            "supplier_id": supplier_ids["Pasar Besar Trading"],
            "line_items": [
                {"ingredient_id": ingredient_ids["Rice"], "quantity": "30"},
                {"ingredient_id": ingredient_ids["Cooking Oil"], "quantity": "15"},
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

    print("\nDone. Login with any of:")
    for _name, email, role in ACCOUNTS:
        print(f"  {role:<28} {email} / {PASSWORD}")


if __name__ == "__main__":
    main()
