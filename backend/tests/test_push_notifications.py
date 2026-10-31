"""FR5.4: device registration and FCM delivery. The real FCM call is replaced
with a recording stub; delivery against a live Firebase project needs real
credentials and can't be exercised here."""
import pytest

from app.models.kitchen import DeviceToken
from app.services import fcm
from app.services import notifications as notification_service
from tests.conftest import auth_headers, register_and_login


@pytest.fixture()
def fcm_calls(monkeypatch):
    """Pretends FCM is configured and records every push; set
    `fcm_calls.result` to change what FCM 'answers'."""

    class Recorder(list):
        result = "sent"

    recorder = Recorder()

    def fake_send(token, title, body, data=None):
        recorder.append({"token": token, "title": title, "body": body, "data": data})
        return recorder.result

    monkeypatch.setattr(fcm, "is_configured", lambda: True)
    monkeypatch.setattr(fcm, "send_to_token", fake_send)
    return recorder


def _kitchen(client):
    token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    headers = auth_headers(token)
    return headers, client.get("/users/me", headers=headers).json()["user_id"]


def _notification_status(client, headers):
    return client.get("/kitchen/notifications", headers=headers).json()[0]["status"]


def test_device_can_be_registered_and_moves_to_whoever_registers_it_last(client, db_session):
    kitchen, kitchen_id = _kitchen(client)
    inventory = auth_headers(register_and_login(client, email="inv@restaurant.com", role="Inventory Staff"))
    inventory_id = client.get("/users/me", headers=inventory).json()["user_id"]

    assert client.post("/notifications/devices", json={"token": "tok-1"}, headers=kitchen).status_code == 201
    assert db_session.query(DeviceToken).one().user_id == kitchen_id

    # A shared tablet passed to someone else must stop notifying the first person.
    client.post("/notifications/devices", json={"token": "tok-1"}, headers=inventory)
    assert db_session.query(DeviceToken).count() == 1
    db_session.expire_all()
    assert db_session.query(DeviceToken).one().user_id == inventory_id


def test_unregister_removes_only_the_callers_device(client, db_session):
    kitchen, _ = _kitchen(client)
    inventory = auth_headers(register_and_login(client, email="inv@restaurant.com", role="Inventory Staff"))
    client.post("/notifications/devices", json={"token": "tok-1"}, headers=kitchen)

    client.post("/notifications/devices/unregister", json={"token": "tok-1"}, headers=inventory)
    assert db_session.query(DeviceToken).count() == 1  # not theirs, so untouched

    client.post("/notifications/devices/unregister", json={"token": "tok-1"}, headers=kitchen)
    assert db_session.query(DeviceToken).count() == 0


def test_notification_is_pushed_and_marked_sent_when_fcm_is_configured(client, db_session, fcm_calls):
    kitchen, kitchen_id = _kitchen(client)
    client.post("/notifications/devices", json={"token": "tok-1"}, headers=kitchen)

    notification_service.notify(db_session, recipient_id=kitchen_id, type_="high_demand_alert", message="Busy Friday")

    assert len(fcm_calls) == 1
    assert fcm_calls[0]["token"] == "tok-1"
    assert fcm_calls[0]["body"] == "Busy Friday"
    assert fcm_calls[0]["title"] == "High demand expected"
    assert _notification_status(client, kitchen) == "sent"


def test_notification_stays_queued_when_the_user_has_no_device(client, db_session, fcm_calls):
    kitchen, kitchen_id = _kitchen(client)

    notification_service.notify(db_session, recipient_id=kitchen_id, type_="prep_update", message="Update")

    assert fcm_calls == []
    assert _notification_status(client, kitchen) == "queued_for_retry"


def test_notification_stays_queued_when_fcm_is_not_configured(client, db_session):
    # No fixture: is_configured() is genuinely False here (no credentials path).
    kitchen, kitchen_id = _kitchen(client)
    client.post("/notifications/devices", json={"token": "tok-1"}, headers=kitchen)

    notification_service.notify(db_session, recipient_id=kitchen_id, type_="prep_update", message="Update")

    assert _notification_status(client, kitchen) == "queued_for_retry"


def test_token_fcm_no_longer_recognises_is_dropped(client, db_session, fcm_calls):
    kitchen, kitchen_id = _kitchen(client)
    client.post("/notifications/devices", json={"token": "stale"}, headers=kitchen)
    fcm_calls.result = "invalid_token"

    notification_service.notify(db_session, recipient_id=kitchen_id, type_="prep_update", message="Update")

    assert db_session.query(DeviceToken).count() == 0
    assert _notification_status(client, kitchen) == "queued_for_retry"


def test_queued_notifications_are_delivered_once_a_device_registers(client, db_session, fcm_calls):
    kitchen, kitchen_id = _kitchen(client)
    notification_service.notify(db_session, recipient_id=kitchen_id, type_="prep_update", message="Missed it")
    assert _notification_status(client, kitchen) == "queued_for_retry"

    client.post("/notifications/devices", json={"token": "tok-1"}, headers=kitchen)
    delivered = notification_service.retry_queued_notifications(db_session)

    assert delivered == 1
    assert len(fcm_calls) == 1
    db_session.expire_all()
    assert _notification_status(client, kitchen) == "sent"
    # And it isn't sent a second time on the next sweep.
    assert notification_service.retry_queued_notifications(db_session) == 0


def test_retry_does_nothing_when_fcm_is_not_configured(client, db_session):
    kitchen, kitchen_id = _kitchen(client)
    notification_service.notify(db_session, recipient_id=kitchen_id, type_="prep_update", message="Update")
    assert notification_service.retry_queued_notifications(db_session) == 0
