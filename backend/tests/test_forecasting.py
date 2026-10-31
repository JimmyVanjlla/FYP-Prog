from datetime import date, timedelta

from tests.conftest import auth_headers, register_and_login


def _manager_token(client):
    return register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")


def _create_menu_item(client, token):
    return client.post(
        "/menu-items",
        json={"name": "Nasi Lemak Ayam", "price": "12.50", "category": "Main"},
        headers=auth_headers(token),
    ).json()


def test_record_order(client):
    """FR4.1's raw input."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)

    resp = client.post(
        "/forecasting/orders",
        json={
            "menu_item_id": item["menu_item_id"],
            "quantity": 3,
            "meal_period": "Lunch",
            "order_date": "2026-08-14",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201


def test_training_skips_item_with_insufficient_data(client):
    """FR4.6 / UC-DF-02 Alt Flow 2a — fewer than MIN_DATA_POINTS orders
    means the item is flagged rather than forced through a fit."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)

    # Only 3 days of data — well under MIN_DATA_POINTS (14).
    base = date(2026, 8, 1)
    for i in range(3):
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": 5,
                "meal_period": "Lunch",
                "order_date": (base + timedelta(days=i)).isoformat(),
            },
            headers=auth_headers(token),
        )

    resp = client.post("/forecasting/train", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["forecasts_created"] == 0
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["reason"] == "insufficient_data"


def test_training_generates_forecasts_with_enough_data(client):
    """FR4.1-FR4.3 — full pipeline: aggregate orders, train Prophet, store
    Forecast rows for the item/meal-period."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)

    # Ends yesterday (relative to whenever this test actually runs), not a
    # hardcoded date — train_and_generate_forecasts only stores rows for
    # forecast_date > today, so historical data has to actually be in the
    # past relative to the real clock for any forecast rows to be created.
    base = date.today() - timedelta(days=30)
    for i in range(30):  # comfortably over MIN_DATA_POINTS
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": 40 + (i % 7),  # mild weekly pattern for Prophet to pick up
                "meal_period": "Lunch",
                "order_date": (base + timedelta(days=i)).isoformat(),
            },
            headers=auth_headers(token),
        )

    resp = client.post("/forecasting/train", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["forecasts_created"] > 0
    assert body["skipped"] == []

    forecasts = client.get(
        "/forecasting/forecasts", params={"menu_item_id": item["menu_item_id"]}, headers=auth_headers(token)
    ).json()
    assert len(forecasts) == body["forecasts_created"]
    assert all(f["meal_period"] == "Lunch" for f in forecasts)
    assert all(float(f["predicted_quantity"]) >= 0 for f in forecasts)


def test_retraining_updates_forecasts_in_place_instead_of_duplicating(client):
    """Regression: every run used to append a fresh Forecast for each future
    date, so the second run doubled everything — and staffing/procurement,
    which sum forecasts, doubled with it. A re-run must update the existing
    rows (same forecast_id) and create none."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    base = date.today() - timedelta(days=30)
    for i in range(30):
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": 40 + (i % 7),
                "meal_period": "Lunch",
                "order_date": (base + timedelta(days=i)).isoformat(),
            },
            headers=auth_headers(token),
        )

    first = client.post("/forecasting/train", headers=auth_headers(token)).json()
    before = client.get("/forecasting/forecasts", headers=auth_headers(token)).json()
    second = client.post("/forecasting/train", headers=auth_headers(token)).json()
    after = client.get("/forecasting/forecasts", headers=auth_headers(token)).json()

    assert first["forecasts_created"] > 0
    assert second["forecasts_created"] == 0
    assert second["forecasts_updated"] == first["forecasts_created"]
    assert len(after) == len(before)
    assert {f["forecast_id"] for f in after} == {f["forecast_id"] for f in before}


def test_availability_explains_why_a_forecast_is_missing(client):
    """FR4.6 / UC-DF-01 Alt Flow 3a — the user is told forecasts aren't
    available yet, and what the minimum is, rather than just seeing nothing."""
    token = _manager_token(client)
    no_history = _create_menu_item(client, token)
    sparse = client.post(
        "/menu-items",
        json={"name": "Mee Goreng", "price": "8.00", "category": "Noodles"},
        headers=auth_headers(token),
    ).json()
    base = date.today() - timedelta(days=10)
    for i in range(3):
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": sparse["menu_item_id"],
                "quantity": 5,
                "meal_period": "Lunch",
                "order_date": (base + timedelta(days=i)).isoformat(),
            },
            headers=auth_headers(token),
        )

    rows = client.get("/forecasting/availability", headers=auth_headers(token)).json()
    by_item = {r["menu_item_id"]: r for r in rows}

    assert by_item[no_history["menu_item_id"]]["available"] is False
    assert by_item[no_history["menu_item_id"]]["data_points"] == 0
    assert "14" in by_item[no_history["menu_item_id"]]["message"]

    assert by_item[sparse["menu_item_id"]]["available"] is False
    assert by_item[sparse["menu_item_id"]]["data_points"] == 3
    assert by_item[sparse["menu_item_id"]]["minimum_required"] == 14
    assert "3 of the 14" in by_item[sparse["menu_item_id"]]["message"]


def test_availability_and_date_filter_once_a_forecast_exists(client):
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    base = date.today() - timedelta(days=30)
    for i in range(30):
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": 40 + (i % 7),
                "meal_period": "Lunch",
                "order_date": (base + timedelta(days=i)).isoformat(),
            },
            headers=auth_headers(token),
        )
    client.post("/forecasting/train", headers=auth_headers(token))

    row = client.get(
        "/forecasting/availability", params={"menu_item_id": item["menu_item_id"]}, headers=auth_headers(token)
    ).json()[0]
    assert row["available"] is True
    assert row["message"] is None

    # UC-DF-01 — filtering the dashboard by date range.
    all_rows = client.get("/forecasting/forecasts", headers=auth_headers(token)).json()
    first_day = min(f["forecast_date"] for f in all_rows)
    narrowed = client.get(
        "/forecasting/forecasts",
        params={"date_from": first_day, "date_to": first_day},
        headers=auth_headers(token),
    ).json()
    assert 0 < len(narrowed) < len(all_rows)
    assert all(f["forecast_date"] == first_day for f in narrowed)


def test_non_manager_cannot_trigger_training(client):
    """FR1.3 RBAC applied to Module 4."""
    token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    resp = client.post("/forecasting/train", headers=auth_headers(token))
    assert resp.status_code == 403


def test_high_leftover_rate_pulls_forecast_down(client, db_session):
    """FR4.5 — a dish with a persistently high leftover rate gets its
    Prophet forecast scaled down, relative to an identical-demand dish
    with no leftover problem."""
    token = _manager_token(client)
    item_normal = _create_menu_item(client, token)
    item_high_leftover = client.post(
        "/menu-items",
        json={"name": "Roti Canai", "price": "3.00", "category": "Side"},
        headers=auth_headers(token),
    ).json()

    base = date.today() - timedelta(days=30)
    for item in (item_normal, item_high_leftover):
        for i in range(30):
            client.post(
                "/forecasting/orders",
                json={
                    "menu_item_id": item["menu_item_id"],
                    "quantity": 40 + (i % 7),
                    "meal_period": "Lunch",
                    "order_date": (base + timedelta(days=i)).isoformat(),
                },
                headers=auth_headers(token),
            )

    # Seed a high leftover rate (40%, well over the 15% default threshold)
    # for item_high_leftover only, within the analysis window.
    from app.models.kitchen import LeftoverLog
    from decimal import Decimal

    kitchen_token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    staff_id = client.get("/users/me", headers=auth_headers(kitchen_token)).json()["user_id"]
    db_session.add(
        LeftoverLog(
            menu_item_id=item_high_leftover["menu_item_id"],
            service_period_date=date.today() - timedelta(days=1),
            prepared_quantity=Decimal("100"),
            leftover_quantity=Decimal("40"),
            leftover_level="Mostly Uneaten",
            staff_id=staff_id,
        )
    )
    db_session.commit()

    client.post("/forecasting/train", headers=auth_headers(token))

    normal_forecasts = client.get(
        "/forecasting/forecasts", params={"menu_item_id": item_normal["menu_item_id"]}, headers=auth_headers(token)
    ).json()
    leftover_forecasts = client.get(
        "/forecasting/forecasts",
        params={"menu_item_id": item_high_leftover["menu_item_id"]},
        headers=auth_headers(token),
    ).json()
    assert normal_forecasts and leftover_forecasts

    avg_normal = sum(float(f["predicted_quantity"]) for f in normal_forecasts) / len(normal_forecasts)
    avg_leftover = sum(float(f["predicted_quantity"]) for f in leftover_forecasts) / len(leftover_forecasts)
    # Both dishes have identical order history, so without the FR4.5
    # adjustment their forecasts would be roughly equal; a clear gap here
    # (not tight equality, since Prophet's fit isn't perfectly
    # deterministic) confirms the leftover-rate signal is actually pulling
    # the forecast down, not just present in a docstring.
    assert avg_leftover < avg_normal * 0.85


def test_list_orders(client):
    """The read side of record_order — historical order data was
    previously write-only."""
    token = _manager_token(client)
    item = _create_menu_item(client, token)
    client.post(
        "/forecasting/orders",
        json={"menu_item_id": item["menu_item_id"], "quantity": 3, "meal_period": "Lunch", "order_date": "2026-08-14"},
        headers=auth_headers(token),
    )

    resp = client.get(
        "/forecasting/orders", params={"menu_item_id": item["menu_item_id"]}, headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["quantity"] == 3


def test_list_forecast_accuracy(client, db_session):
    """FR4.4 — "track forecast accuracy" needs direct API access, not
    just a figure buried inside the weekly PDF report."""
    from decimal import Decimal

    from app.models.forecasting import Forecast, ForecastAccuracy

    token = _manager_token(client)
    item = _create_menu_item(client, token)
    forecast = Forecast(
        menu_item_id=item["menu_item_id"],
        meal_period="Lunch",
        forecast_date=date(2026, 8, 20),
        predicted_quantity=Decimal("100.00"),
    )
    db_session.add(forecast)
    db_session.flush()
    db_session.add(
        ForecastAccuracy(forecast_id=forecast.forecast_id, actual_quantity=Decimal("95.00"), accuracy_error=Decimal("0.05"))
    )
    db_session.commit()

    resp = client.get(
        "/forecasting/accuracy", params={"menu_item_id": item["menu_item_id"]}, headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["actual_quantity"] == "95.00"


def test_high_demand_forecast_triggers_alert(client):
    """FR5.4 / UC-KO-04 — a forecast well above the item's historical
    average notifies Kitchen Staff."""
    manager_token = _manager_token(client)
    item = _create_menu_item(client, manager_token)
    kitchen_token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")

    # A strong upward trend: low and flat for the first three weeks, then a
    # sharp step up for the last few days, so Prophet's near-term forecast
    # continues near the recent high — well above the overall historical
    # mean (which is dragged down by the long flat stretch at the start).
    base = date.today() - timedelta(days=28)
    for i in range(28):
        quantity = 10 if i < 21 else 200
        client.post(
            "/forecasting/orders",
            json={
                "menu_item_id": item["menu_item_id"],
                "quantity": quantity,
                "meal_period": "Lunch",
                "order_date": (base + timedelta(days=i)).isoformat(),
            },
            headers=auth_headers(manager_token),
        )

    client.post("/forecasting/train", headers=auth_headers(manager_token))

    notifications = client.get("/kitchen/notifications", headers=auth_headers(kitchen_token)).json()
    high_demand = [n for n in notifications if n["type"] == "high_demand_alert"]
    assert len(high_demand) > 0
