"""
Gets the live demo system into a presentable state in one go. Run it the
evening before (and again on the morning of) a presentation:

    python scripts/extend_demo_orders.py --base-url https://fyp-prog.onrender.com
    python scripts/prepare_demo.py --base-url https://fyp-prog.onrender.com

extend_demo_orders.py fills order history up to yesterday; this script then
does everything that depends on that history or that a demo flow needs waiting:

  1. adds leftover logs for the last 7 days (each one also records its waste
     cost), so the waste section of a report and Algorithm 2 have data;
  2. retrains forecasts (they cover the 7 days after the last order);
  3. re-runs the leftover analysis (Algorithm 2), so portion reviews exist;
  4. regenerates the procurement "recommended to buy" list;
  5. makes sure the Manager has a purchase order waiting for approval;
  6. makes sure there is a delivery waiting for Delivery staff to confirm;
  7. makes sure Inventory staff has a (kitchen-raised) restock request to look at;
  8. generates a weekly report for the 7 days ending today.

It only adds what is missing, so running it twice is safe. It never deletes
anything, and it uses the seed accounts (password from seed_dev_data.py).
"""
import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import seed_dev_data as seed  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--password", default=seed.PASSWORD)
    args = ap.parse_args()

    c = httpx.Client(base_url=args.base_url, timeout=240)

    def login(email: str) -> dict:
        r = c.post("/auth/login", json={"email": email, "password": args.password})
        r.raise_for_status()
        return {"Authorization": "Bearer " + r.json()["access_token"]}

    manager = login("manager@test.com")
    procurement = login("procurement@test.com")
    inventory = login("inventory@test.com")
    kitchen = login("kitchen@test.com")

    def rows(path: str, headers: dict, **query) -> list:
        r = c.get(path, headers=headers, params={"limit": 500, **query})
        r.raise_for_status()
        return r.json()

    print("0. Leftover logs for the last 7 days")
    menu = {m["name"]: m["menu_item_id"] for m in rows("/menu-items", manager)}
    demand = {name: avg for name, _c, _p, _r, avg in seed.MENU_ITEMS}
    logs = rows("/kitchen/leftover-logs", manager)
    last_logged = max((date.fromisoformat(l["service_period_date"]) for l in logs), default=date.today() - timedelta(days=8))
    rng = random.Random(date.today().toordinal())
    added = 0
    day = max(last_logged + timedelta(days=1), date.today() - timedelta(days=7))
    while day < date.today():
        for name, mid in menu.items():
            if name not in demand:
                continue
            prepared = max(2, round(demand[name] * 0.5 * rng.uniform(0.9, 1.1)))
            rate = rng.uniform(0.25, 0.38) if name in seed.HIGH_LEFTOVER_ITEMS else rng.uniform(0.03, 0.12)
            c.post(
                "/kitchen/leftover-logs",
                headers=kitchen,
                json={
                    "menu_item_id": mid,
                    "service_period_date": day.isoformat(),
                    "prepared_quantity": prepared,
                    "leftover_quantity": max(0, round(prepared * rate)),
                    "leftover_level": "Mostly Uneaten" if rate > 0.2 else "Partially Eaten",
                },
            ).raise_for_status()
            added += 1
        day += timedelta(days=1)
    print(f"   added {added} leftover logs")

    print("1. Training forecasts (about a minute on the free server)")
    print("  ", c.post("/forecasting/train", headers=manager).raise_for_status().json())

    print("2. Analysing leftover rates")
    print("  ", c.post("/portion-feedback/analyze", headers=manager).raise_for_status().json())

    print("3. Regenerating procurement recommendations")
    r = c.post("/procurement/recommendations/generate", headers=procurement)
    r.raise_for_status()
    print(f"   {len(r.json())} recommendations")

    suppliers = {s["name"]: s["supplier_id"] for s in rows("/procurement/suppliers", procurement)}
    ingredients = {i["name"]: i["ingredient_id"] for i in rows("/inventory/ingredients", manager)}
    orders = rows("/procurement/purchase-orders", manager)

    print("4. A purchase order waiting for the Manager")
    if any(o["status"] == "pending_approval" for o in orders):
        print("   already one pending")
    else:
        po = c.post(
            "/procurement/purchase-orders",
            headers=procurement,
            json={
                "supplier_id": suppliers["Fresh Farm Poultry & Seafood"],
                "line_items": [
                    {"ingredient_id": ingredients["Chicken"], "quantity": "20"},
                    {"ingredient_id": ingredients["Prawns"], "quantity": "10"},
                ],
            },
        )
        po.raise_for_status()
        print(f"   created PO #{po.json()['po_id']} (pending approval)")

    print("5. A delivery waiting for Delivery staff")
    deliveries = rows("/deliveries", manager)
    waiting = [d for d in deliveries if d["status"] in ("awaiting_delivery", "in_transit")]
    if waiting:
        print(f"   already {len(waiting)} waiting")
    else:
        approved = [o for o in orders if o["status"] == "approved"]
        scheduled = {d["po_id"] for d in deliveries}
        todo = [o for o in approved if o["po_id"] not in scheduled]
        if todo:
            d = c.post(
                "/deliveries",
                headers=procurement,
                json={"po_id": todo[0]["po_id"], "scheduled_date": date.today().isoformat()},
            )
            d.raise_for_status()
            print(f"   scheduled a delivery for PO #{todo[0]['po_id']}")
        else:
            print("   nothing to schedule (approve a purchase order first, then re-run)")

    print("6. A restock request from the kitchen for Inventory staff")
    if rows("/inventory/restocking-requests", inventory):
        print("   already present")
    else:
        low = [i for i in rows("/inventory/ingredients", inventory) if i.get("is_low_stock")]
        if low:
            c.post(
                "/inventory/restocking-requests",
                headers=kitchen,  # raised by Kitchen staff, handled by Inventory staff
                json={"ingredient_id": low[0]["ingredient_id"], "quantity": "20", "urgency": True},
            ).raise_for_status()
            print(f"   requested {low[0]['name']}")

    print("7. Weekly report for the 7 days ending today")
    end = date.today()
    start = end - timedelta(days=6)
    existing = rows("/reports", manager)
    if any(r["period_start"] == start.isoformat() for r in existing):
        print("   already generated")
    else:
        r = c.post("/reports/weekly", headers=manager, json={"period_start": start.isoformat(), "period_end": end.isoformat()})
        print("  ", r.status_code, r.text[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
