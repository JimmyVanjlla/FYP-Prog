"""
Extends the demo order history up to yesterday, so the forecasts a demo shows
cover the coming days instead of stopping where the seed data stopped.

A forecast run predicts the 7 days after the LAST order it has seen, and only
stores dates after today. Seeded history ending on 27 Oct therefore gives
nothing useful after 3 Nov. Run this on the morning of a demo (or the night
before), then trigger training.

Uses the same generator as scripts/seed_dev_data.py (weekend uplift, gentle
trend, 15% noise) and is safe to run twice: it reads each menu item's existing
orders and only adds the (date, meal period) pairs that are missing.

    python scripts/extend_demo_orders.py --base-url https://fyp-prog.onrender.com
    python scripts/extend_demo_orders.py --base-url http://127.0.0.1:8000 --dry-run
"""
import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import seed_dev_data as seed  # noqa: E402

PERIOD_SHARE = {"Lunch": 0.55, "Dinner": 0.45}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--email", default="manager@test.com")
    ap.add_argument("--password", default=seed.PASSWORD)
    ap.add_argument("--to", type=date.fromisoformat, default=date.today() - timedelta(days=1), help="last day to fill (default: yesterday)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=120)
    token = client.post("/auth/login", json={"email": args.email, "password": args.password}).raise_for_status().json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    items = client.get("/menu-items", headers=headers, params={"limit": 500}).raise_for_status().json()
    demand = {name: avg for name, _c, _p, _r, avg in seed.MENU_ITEMS}
    rng = random.Random(args.to.toordinal())  # same output for the same target date

    existing: dict[int, set[tuple[date, str]]] = {}
    earliest = None
    for item in items:
        if item["name"] not in demand:
            continue
        rows = client.get(
            "/forecasting/orders", headers=headers, params={"menu_item_id": item["menu_item_id"], "limit": 500}
        ).raise_for_status().json()
        have = {(date.fromisoformat(r["order_date"]), r["meal_period"]) for r in rows}
        existing[item["menu_item_id"]] = have
        if have:
            first = min(d for d, _ in have)
            earliest = first if earliest is None else min(earliest, first)
    if earliest is None:
        print("No existing orders found; run scripts/seed_dev_data.py first.")
        return 1

    horizon_days = seed.WEEKS_OF_ORDER_HISTORY * 7  # the generator's trend is defined over the seeded span
    created = skipped = 0
    for item in items:
        if item["name"] not in demand:
            continue
        have = existing[item["menu_item_id"]]
        last = max((d for d, _ in have), default=None)
        if last is None:
            continue
        day = last + timedelta(days=1)
        while day <= args.to:
            offset = (day - earliest).days
            boost = 1.3 if day.weekday() >= 5 else 1.0
            trend = 1.0 + 0.15 * (offset / horizon_days)
            for period, share in PERIOD_SHARE.items():
                if (day, period) in have:
                    skipped += 1
                    continue
                mean = demand[item["name"]] * share * boost * trend
                quantity = max(1, round(rng.gauss(mean, mean * 0.15)))
                if not args.dry_run:
                    client.post(
                        "/forecasting/orders",
                        headers=headers,
                        json={
                            "menu_item_id": item["menu_item_id"],
                            "quantity": quantity,
                            "meal_period": period,
                            "order_date": day.isoformat(),
                        },
                    ).raise_for_status()
                created += 1
            day += timedelta(days=1)
        print(f"  {item['name']}: filled through {args.to}" if not args.dry_run else f"  {item['name']}: would fill {last + timedelta(days=1)} to {args.to}", flush=True)

    verb = "would add" if args.dry_run else "added"
    print(f"{verb} {created} orders; {skipped} already present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
