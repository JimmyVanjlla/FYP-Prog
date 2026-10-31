"""UC-RA-01: read a report's figures in the app, and retry a failed one."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from app.models.forecasting import Forecast, ForecastAccuracy
from app.models.report import Report
from app.models.waste import WasteLog
from tests.conftest import auth_headers, register_and_login


def _report_with_data(client, db_session):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    item = client.post(
        "/menu-items", json={"name": "Nasi Lemak", "price": "6.50", "category": "Rice"}, headers=manager
    ).json()
    inventory = auth_headers(register_and_login(client, email="inv@restaurant.com", role="Inventory Staff"))
    ingredient = client.post(
        "/inventory/ingredients", json={"name": "Rice", "unit": "kg", "current_stock": "10"}, headers=inventory
    ).json()

    period_end = date.today() - timedelta(days=1)
    period_start = period_end - timedelta(days=6)
    forecast = Forecast(
        menu_item_id=item["menu_item_id"],
        meal_period="Lunch",
        forecast_date=period_start + timedelta(days=1),
        predicted_quantity=Decimal("100.00"),
    )
    db_session.add(forecast)
    db_session.flush()
    db_session.add(
        ForecastAccuracy(forecast_id=forecast.forecast_id, actual_quantity=Decimal("90.00"), accuracy_error=Decimal("0.1000"))
    )
    db_session.add(
        WasteLog(
            source_type="leftover",
            source_ref_id=1,
            ingredient_id=ingredient["ingredient_id"],
            quantity_wasted=Decimal("2.000"),
            waste_cost=Decimal("6.40"),
            logged_at=datetime.combine(period_start + timedelta(days=2), time(12, 0), tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    report = client.post(
        "/reports/weekly",
        json={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
        headers=manager,
    ).json()
    return manager, report


def test_summary_returns_the_three_report_sections_as_data(client, db_session):
    manager, report = _report_with_data(client, db_session)

    summary = client.get(f"/reports/{report['report_id']}/summary", headers=manager).json()

    assert summary["forecast_accuracy"]["scored_forecasts"] == 1
    assert summary["forecast_accuracy"]["mean_error"] == 0.1
    assert summary["forecast_accuracy"]["rows"][0]["predicted"] == "100.00"
    assert summary["waste"]["log_count"] == 1
    assert summary["waste"]["total_cost"] == "6.40"
    assert "utilisation_pct" in summary["budget"]


def test_summary_of_unknown_report_is_404(client):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    assert client.get("/reports/999/summary", headers=manager).status_code == 404


def test_failed_report_can_be_regenerated_in_place(client, db_session):
    """Alt Flow 4a: same report, same period: not a second report."""
    manager, report = _report_with_data(client, db_session)
    row = db_session.get(Report, report["report_id"])
    row.status = "failed"
    row.pdf_path = None
    db_session.commit()

    resp = client.post(f"/reports/{report['report_id']}/regenerate", headers=manager)

    assert resp.status_code == 200
    body = resp.json()
    assert body["report_id"] == report["report_id"]
    assert body["status"] == "generated"
    assert body["pdf_path"]
    assert len(client.get("/reports", headers=manager).json()) == 1


def test_regenerate_unknown_report_is_404_and_non_managers_are_refused(client, db_session):
    manager, _ = _report_with_data(client, db_session)
    assert client.post("/reports/999/regenerate", headers=manager).status_code == 404

    kitchen = auth_headers(register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff"))
    assert client.post("/reports/1/regenerate", headers=kitchen).status_code == 403
    assert client.get("/reports/1/summary", headers=kitchen).status_code == 403
