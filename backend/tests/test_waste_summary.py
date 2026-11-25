"""Waste dated by service day, the weekly summary, and the data migration."""
import importlib.util
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.core.dates import restaurant_today
from app.models.waste import WasteLog
from app.services import waste as waste_service
from tests.conftest import auth_headers, register_and_login


def _setup_dish(client):
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    inv = register_and_login(client, email="inv@restaurant.com", role="Shift Supervisor")
    kitchen = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    item = client.post(
        "/menu-items", json={"name": "Curry Laksa", "price": "8.00", "category": "Noodles"}, headers=auth_headers(manager)
    ).json()
    ingredient = client.post(
        "/inventory/ingredients", json={"name": "Coconut Milk", "unit": "litre", "current_stock": "50"}, headers=auth_headers(inv)
    ).json()
    client.post(
        f"/menu-items/{item['menu_item_id']}/recipe-links",
        json={"ingredient_id": ingredient["ingredient_id"], "quantity_per_serving": "0.1"},
        headers=auth_headers(manager),
    )
    return manager, kitchen, item, ingredient


def _leftover(client, kitchen, item, day, quantity="5"):
    return client.post(
        "/kitchen/leftover-logs",
        json={
            "menu_item_id": item["menu_item_id"],
            "service_period_date": day.isoformat(),
            "prepared_quantity": "20",
            "leftover_quantity": quantity,
            "leftover_level": "Partially Eaten",
        },
        headers=auth_headers(kitchen),
    )


def test_a_leftover_is_recorded_on_its_service_day_not_when_typed_in(client):
    manager, kitchen, item, _ = _setup_dish(client)
    three_days_ago = restaurant_today() - timedelta(days=3)
    assert _leftover(client, kitchen, item, three_days_ago).status_code == 201

    log = client.get("/waste/logs", headers=auth_headers(manager)).json()[0]
    assert log["logged_at"].startswith(three_days_ago.isoformat())


def test_summary_groups_cost_by_week_and_names_the_biggest_sources(client):
    manager, kitchen, item, ingredient = _setup_dish(client)
    today = restaurant_today()
    this_monday = today - timedelta(days=today.weekday())
    last_week_day = this_monday - timedelta(days=3)

    _leftover(client, kitchen, item, last_week_day, "5")
    _leftover(client, kitchen, item, last_week_day - timedelta(days=1), "5")

    body = client.get("/waste/summary", params={"weeks": 4}, headers=auth_headers(manager)).json()
    assert len(body["weeks"]) == 4
    assert body["weeks"][-1]["period_start"] == this_monday.isoformat()  # the current week is last
    weeks_with_waste = [w for w in body["weeks"] if w["entries"]]
    assert sum(w["entries"] for w in weeks_with_waste) == 2
    assert body["weeks"][-1]["entries"] == 0  # nothing logged this week
    # Unpriced ingredients cost nothing, but the ingredient and dish still show up.
    assert body["top_ingredients"][0]["name"] == "Coconut Milk"
    assert body["top_ingredients"][0]["quantity"] == "1.000"  # 2 logs x 5 servings x 0.1 litre
    assert body["top_dishes"][0]["name"] == "Curry Laksa"


def test_summary_is_empty_but_well_formed_with_no_waste(client):
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    body = client.get("/waste/summary", headers=auth_headers(manager)).json()
    assert len(body["weeks"]) == 8
    assert body["top_ingredients"] == [] and body["top_dishes"] == []


def test_migration_redates_leftover_waste_to_the_service_day(client, db_session):
    manager, kitchen, item, ingredient = _setup_dish(client)
    long_ago = date(2026, 10, 7)
    assert _leftover(client, kitchen, item, long_ago).status_code == 201
    # Simulate the old behaviour: the waste log was stamped when it was typed in.
    log = db_session.query(WasteLog).one()
    log.logged_at = datetime(2026, 10, 28, 9, 30, tzinfo=timezone.utc)
    db_session.commit()

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "5d1e8a7c3b92_waste_logs_dated_by_service_day.py"
    spec = importlib.util.spec_from_file_location("waste_redate_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = db_session.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
    db_session.expire_all()

    assert db_session.query(WasteLog).one().logged_at.date() == long_ago
