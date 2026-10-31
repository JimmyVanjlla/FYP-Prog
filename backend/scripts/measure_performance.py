"""
Measures the three performance targets in Chapter 3 (NFR-Performance) so they
are numbers rather than claims:

  * API responses within 2 seconds under normal load        (--api)
  * a full Prophet training cycle within 60 s for 100 items (--forecast)
  * the weekly PDF report within 30 s                       (--report)

Usage (from backend/, venv active):
    python scripts/measure_performance.py --forecast 100
    python scripts/measure_performance.py --report
    python scripts/measure_performance.py --api        # needs the server running

--forecast and --report build a throwaway SQLite database with synthetic data,
so they never touch the real one. --api talks to a running server as a Manager
account (defaults to the seeded manager@test.com; override with --email/--password).
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import tempfile
import time
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

API_TARGET_SECONDS = 2.0
FORECAST_TARGET_SECONDS = 60.0
REPORT_TARGET_SECONDS = 30.0


def _verdict(seconds: float, target: float) -> str:
    return f"{seconds:6.2f}s  ({'within' if seconds <= target else 'OVER'} the {target:.0f}s target)"


def _scratch_session():
    """A fresh SQLite database with the full schema, deleted on exit."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.base_all import Base

    path = os.path.join(tempfile.mkdtemp(), "perf.db")
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_orders(db, items: int, weeks: int = 8, meal_periods=("Lunch",)):
    from app.models.forecasting import Order
    from app.models.menu import MenuItem

    start = date.today() - timedelta(days=weeks * 7)
    ids = []
    for i in range(items):
        item = MenuItem(name=f"Dish {i}", price=Decimal("8.00"), category="Main", is_active=True)
        db.add(item)
        db.flush()
        ids.append(item.menu_item_id)
        base = random.randint(15, 60)
        for day in range(weeks * 7):
            d = start + timedelta(days=day)
            for period in meal_periods:
                qty = max(1, round(random.gauss(base * (1.3 if d.weekday() >= 5 else 1.0), base * 0.15)))
                db.add(Order(menu_item_id=item.menu_item_id, quantity=qty, meal_period=period, order_date=d))
    db.commit()
    return ids


def measure_forecast(items: int) -> float:
    from app.services.forecasting import train_and_generate_forecasts

    db = _scratch_session()
    print(f"Seeding {items} menu items x 8 weeks of orders...")
    _seed_orders(db, items)
    print("Training (one Prophet model per item/meal period)...")
    started = time.perf_counter()
    result = train_and_generate_forecasts(db)
    elapsed = time.perf_counter() - started
    print(f"  models trained: {items - len(result['skipped'])}, forecasts stored: {result['forecasts_created']}")
    print(f"FORECAST CYCLE for {items} items: {_verdict(elapsed, FORECAST_TARGET_SECONDS)}")
    return elapsed


def measure_report() -> float:
    from app.models.forecasting import Forecast, ForecastAccuracy
    from app.models.inventory import Ingredient
    from app.models.waste import WasteLog
    from app.services.reporting import generate_weekly_report

    db = _scratch_session()
    ids = _seed_orders(db, 50)
    ingredient = Ingredient(name="Rice", unit="kg", current_stock=Decimal("100"))
    db.add(ingredient)
    db.flush()
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=6)
    for mid in ids:
        for offset in range(7):
            f = Forecast(
                menu_item_id=mid,
                meal_period="Lunch",
                forecast_date=start + timedelta(days=offset),
                predicted_quantity=Decimal("40.00"),
            )
            db.add(f)
            db.flush()
            db.add(ForecastAccuracy(forecast_id=f.forecast_id, actual_quantity=Decimal("38.00"), accuracy_error=Decimal("0.0500")))
        db.add(
            WasteLog(
                source_type="leftover",
                source_ref_id=mid,
                ingredient_id=ingredient.ingredient_id,
                quantity_wasted=Decimal("1.000"),
                waste_cost=Decimal("3.20"),
            )
        )
    db.commit()

    started = time.perf_counter()
    report = generate_weekly_report(db, period_start=start, period_end=end)
    elapsed = time.perf_counter() - started
    size_kb = os.path.getsize(report.pdf_path) / 1024
    print(f"  PDF: {size_kb:.0f} KB from 350 scored forecasts and 50 waste logs")
    print(f"WEEKLY PDF: {_verdict(elapsed, REPORT_TARGET_SECONDS)}")
    return elapsed


def measure_api(base_url: str, rounds: int, email: str, password: str) -> float:
    import httpx

    client = httpx.Client(base_url=base_url, timeout=30)
    login = client.post("/auth/login", json={"email": email, "password": password})
    login.raise_for_status()
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    endpoints = [
        "/users/me",
        "/menu-items",
        "/inventory/ingredients",
        "/inventory/ingredients/low-stock",
        "/forecasting/forecasts?limit=100",
        "/forecasting/availability",
        "/forecasting/orders?limit=100",
        "/kitchen/prep-recommendations",
        "/waste/logs?limit=100",
        "/waste/trends",
        "/portion-feedback/recommendations",
        "/procurement/purchase-orders",
        "/procurement/budget/utilisation",
        "/deliveries",
        "/staffing/schedules",
        "/reports",
        "/config",
    ]
    worst = 0.0
    print(f"{'endpoint':<44}{'median':>8}{'p95':>8}{'max':>8}")
    for path in endpoints:
        times = []
        for _ in range(rounds):
            started = time.perf_counter()
            response = client.get(path, headers=headers)
            times.append(time.perf_counter() - started)
            response.raise_for_status()
        times.sort()
        p95 = times[min(len(times) - 1, int(len(times) * 0.95))]
        worst = max(worst, times[-1])
        flag = "" if times[-1] <= API_TARGET_SECONDS else "  <-- OVER"
        print(f"{path:<44}{statistics.median(times):>7.2f}s{p95:>7.2f}s{times[-1]:>7.2f}s{flag}")
    print(f"API slowest single response: {_verdict(worst, API_TARGET_SECONDS)}")
    return worst


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--forecast", type=int, metavar="N_ITEMS", help="time a full training cycle for N menu items")
    parser.add_argument("--report", action="store_true", help="time weekly PDF generation")
    parser.add_argument("--api", action="store_true", help="time the API endpoints on a running server")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--rounds", type=int, default=5, help="requests per endpoint for --api")
    parser.add_argument("--email", default="manager@test.com", help="a Manager account, for --api")
    parser.add_argument("--password", default="Password123!")
    args = parser.parse_args()

    if not (args.forecast or args.report or args.api):
        parser.print_help()
    if args.api:
        measure_api(args.base_url, args.rounds, args.email, args.password)
    if args.report:
        measure_report()
    if args.forecast:
        measure_forecast(args.forecast)
