"""The weekly report also carries the % leftover calculation and the staff
assignments for the period."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from app.models.kitchen import LeftoverLog
from app.models.staffing import ShiftAssignment, ShiftSchedule
from app.models.user import User
from app.models.waste import WasteLog
from tests.conftest import auth_headers, register_and_login


def _setup(client, db_session):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    register_and_login(client, email="sup@restaurant.com", role="Shift Supervisor")
    register_and_login(client, email="aisha@restaurant.com", role="Kitchen Staff")
    register_and_login(client, email="bo@restaurant.com", role="Kitchen Staff")
    laksa = client.post("/menu-items", json={"name": "Curry Laksa", "price": "8.00", "category": "Noodles"}, headers=manager).json()
    roti = client.post("/menu-items", json={"name": "Roti Telur", "price": "4.00", "category": "Bread"}, headers=manager).json()

    kitchen_users = {u.email: u for u in db_session.query(User).all()}
    day = date.today() - timedelta(days=2)
    start, end = day - timedelta(days=3), day + timedelta(days=1)

    def log(item, prepared, leftover, when):
        db_session.add(
            LeftoverLog(
                menu_item_id=item["menu_item_id"],
                service_period_date=when,
                meal_period="Lunch",
                prepared_quantity=Decimal(prepared),
                leftover_quantity=Decimal(leftover),
                leftover_percent=round(float(leftover) / float(prepared) * 100),
                leftover_level="x",
                staff_id=kitchen_users["aisha@restaurant.com"].user_id,
            )
        )

    log(laksa, "40", "10", day)  # 25 per cent
    log(laksa, "40", "6", day - timedelta(days=1))
    log(roti, "20", "2", day)
    db_session.add(
        WasteLog(
            source_type="leftover",
            source_ref_id=1,
            ingredient_id=1,
            quantity_wasted=Decimal("1.000"),
            waste_cost=Decimal("5.00"),
            logged_at=datetime.combine(day, time(12, 0), tzinfo=timezone.utc),
        )
    )

    published = ShiftSchedule(date=day, meal_period="Lunch", published_by=kitchen_users["sup@restaurant.com"].user_id, status="published")
    draft = ShiftSchedule(date=day, meal_period="Dinner", published_by=kitchen_users["sup@restaurant.com"].user_id, status="draft")
    db_session.add_all([published, draft])
    db_session.flush()
    for email in ("aisha@restaurant.com", "bo@restaurant.com"):
        db_session.add(ShiftAssignment(schedule_id=published.schedule_id, staff_id=kitchen_users[email].user_id, station="Kitchen"))
    db_session.add(ShiftAssignment(schedule_id=draft.schedule_id, staff_id=kitchen_users["bo@restaurant.com"].user_id, station="Kitchen"))
    db_session.commit()
    return manager, start, end, day


def test_the_report_shows_the_leftover_percentage_calculation(client, db_session):
    manager, start, end, day = _setup(client, db_session)
    # an ingredient for the waste log's foreign key
    client.post(
        "/inventory/ingredients", json={"name": "Coconut Milk", "unit": "litre", "current_stock": "9"}, headers=manager
    )
    report = client.post("/reports/weekly", json={"period_start": start.isoformat(), "period_end": end.isoformat()}, headers=manager).json()
    summary = client.get(f"/reports/{report['report_id']}/summary", headers=manager).json()

    left = summary["leftover"]
    assert (left["prepared"], left["leftover"], left["served"]) == (100.0, 18.0, 82.0)
    assert round(left["leftover_percent"], 1) == 18.0
    laksa = next(d for d in left["dishes"] if d["menu_item_name"] == "Curry Laksa")
    assert (laksa["prepared"], laksa["served"], laksa["leftover"]) == (80.0, 64.0, 16.0)
    assert round(laksa["leftover_percent"], 1) == 20.0
    assert left["dishes"][0]["menu_item_name"] == "Curry Laksa"  # highest share left over first


def test_the_report_lists_the_published_shifts_with_who_was_assigned(client, db_session):
    manager, start, end, day = _setup(client, db_session)
    client.post(
        "/inventory/ingredients", json={"name": "Coconut Milk", "unit": "litre", "current_stock": "9"}, headers=manager
    )
    report = client.post("/reports/weekly", json={"period_start": start.isoformat(), "period_end": end.isoformat()}, headers=manager).json()
    shifts = client.get(f"/reports/{report['report_id']}/summary", headers=manager).json()["staffing"]

    assert len(shifts) == 1  # the draft Dinner schedule is not a duty yet
    assert shifts[0]["date"] == day.isoformat() and shifts[0]["meal_period"] == "Lunch"
    assert [(p["station"]) for p in shifts[0]["staff"]] == ["Kitchen", "Kitchen"]
    assert len(shifts[0]["staff"]) == 2


def test_the_pdf_builds_with_the_new_sections(client, db_session):
    manager, start, end, _ = _setup(client, db_session)
    client.post(
        "/inventory/ingredients", json={"name": "Coconut Milk", "unit": "litre", "current_stock": "9"}, headers=manager
    )
    report = client.post("/reports/weekly", json={"period_start": start.isoformat(), "period_end": end.isoformat()}, headers=manager).json()
    resp = client.get(f"/reports/{report['report_id']}/download", headers=manager)
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")
    assert resp.content.count(b"/Type /Page\n") + resp.content.count(b"/Type /Page ") >= 3 or b"/Count 3" in resp.content
