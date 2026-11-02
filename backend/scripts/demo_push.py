"""
Sends a real push notification during a demo, from the laptop, while the app
on the emulator is in the background.

It acts as a Kitchen Staff user and confirms one prep recommendation with a
large change from the recommended quantity. That is a normal action that the
system answers with a "prep update" notification to every Kitchen Staff phone.
Each recommendation can only be confirmed once, so this uses one up per run.

    python scripts/demo_push.py --base-url https://fyp-prog.onrender.com
    python scripts/demo_push.py --base-url ... --date 2026-11-03 --period Dinner
"""
import argparse
from datetime import date
from decimal import Decimal

import httpx

PASSWORD = "Password123!"  # the dev seed password, see scripts/seed_dev_data.py


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--email", default="kitchen@test.com")
    ap.add_argument("--password", default=PASSWORD)
    ap.add_argument("--date", type=date.fromisoformat, default=date.today())
    ap.add_argument("--period", default="Lunch", choices=["Breakfast", "Lunch", "Dinner"])
    args = ap.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=120)
    token = client.post("/auth/login", json={"email": args.email, "password": args.password}).raise_for_status().json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    recs = client.get(
        "/kitchen/prep-recommendations",
        headers=headers,
        params={"forecast_date": args.date.isoformat(), "meal_period": args.period, "limit": 500},
    ).raise_for_status().json()
    open_recs = [r for r in recs if not r["confirmed"] and Decimal(r["recommended_quantity"]) > 0]
    if not open_recs:
        print(
            f"No unconfirmed prep recommendations for {args.date} {args.period}. "
            "Open the Prep screen once as Kitchen (it creates them from the forecasts), or pick another date/period."
        )
        return 1

    rec = open_recs[0]
    recommended = Decimal(rec["recommended_quantity"])
    quantity = (recommended * Decimal("1.8")).quantize(Decimal("0.01"))
    resp = client.post(
        f"/kitchen/prep-recommendations/{rec['recommendation_id']}/confirm",
        headers=headers,
        json={"confirmed_quantity": str(quantity), "deviation_reason": "Large booking expected"},
    )
    resp.raise_for_status()
    print(f"Confirmed recommendation #{rec['recommendation_id']} at {quantity} (recommended {recommended}).")
    print("A 'Prep update' push should appear on every phone logged in as Kitchen Staff within a few seconds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
