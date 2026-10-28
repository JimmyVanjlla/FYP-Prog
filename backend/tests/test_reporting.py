import os
from datetime import date, timedelta
from decimal import Decimal

from app.models.forecasting import Forecast, ForecastAccuracy
from app.models.waste import WasteLog
from tests.conftest import auth_headers, register_and_login


def _manager_token(client):
    return register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")


def test_weekly_report_rejects_empty_period(client):
    """FR11.6."""
    token = _manager_token(client)
    resp = client.post(
        "/reports/weekly",
        json={"period_start": "2020-01-01", "period_end": "2020-01-07"},  # nothing exists in this range
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


def test_weekly_report_generates_pdf_with_data(client, db_session):
    """FR11.1 / FR11.2 / FR11.3 / FR11.4."""
    token = _manager_token(client)
    item = client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
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
        ForecastAccuracy(forecast_id=forecast.forecast_id, actual_quantity=Decimal("95.00"), accuracy_error=Decimal("0.05"))
    )

    inv_token = register_and_login(client, email="inv@restaurant.com", role="Inventory Staff")
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Chicken Thigh", "unit": "kg", "current_stock": "10"},
        headers=auth_headers(inv_token),
    ).json()
    db_session.add(
        WasteLog(
            source_type="leftover",
            source_ref_id=1,
            ingredient_id=ingredient["ingredient_id"],
            quantity_wasted=Decimal("2.000"),
            waste_cost=Decimal("18.40"),
        )
    )
    db_session.commit()

    resp = client.post(
        "/reports/weekly",
        json={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "generated"
    assert body["pdf_path"] is not None
    assert os.path.exists(body["pdf_path"])
    assert os.path.getsize(body["pdf_path"]) > 0

    # FR11.2 — the generated PDF can actually be downloaded back.
    download = client.get(f"/reports/{body['report_id']}/download", headers=auth_headers(token))
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"

    # A plain browser tab (Flutter's "open the PDF" flow) can't set an
    # Authorization header, so the same endpoint also accepts ?token=.
    download_via_query = client.get(f"/reports/{body['report_id']}/download?token={token}")
    assert download_via_query.status_code == 200


def test_weekly_report_includes_waste_logged_today_when_period_end_is_today(client, db_session):
    """Regression test: WasteLog.logged_at is a timezone-aware datetime,
    and period_end is a bare date — comparing `logged_at <= period_end`
    casts period_end to midnight at the *start* of that day, which used to
    silently exclude anything logged later the same day. A report whose
    period_end is today, generated right now, should still include waste
    logged earlier today (see app/services/reporting.py::_end_of_day)."""
    token = _manager_token(client)
    inv_token = register_and_login(client, email="inv2@restaurant.com", role="Inventory Staff")
    ingredient = client.post(
        "/inventory/ingredients",
        json={"name": "Prawns", "unit": "kg", "current_stock": "10"},
        headers=auth_headers(inv_token),
    ).json()
    # No explicit logged_at — defaults to "now" (today), same as a real
    # WasteLog created by record_leftover_waste earlier today.
    db_session.add(
        WasteLog(
            source_type="leftover",
            source_ref_id=1,
            ingredient_id=ingredient["ingredient_id"],
            quantity_wasted=Decimal("1.000"),
            waste_cost=Decimal("9.80"),
        )
    )
    db_session.commit()

    today = date.today()
    resp = client.post(
        "/reports/weekly",
        json={"period_start": (today - timedelta(days=6)).isoformat(), "period_end": today.isoformat()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201


def test_non_manager_cannot_generate_report(client):
    """FR1.3 RBAC applied to Module 11."""
    token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    resp = client.post(
        "/reports/weekly",
        json={"period_start": "2026-08-01", "period_end": "2026-08-07"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
