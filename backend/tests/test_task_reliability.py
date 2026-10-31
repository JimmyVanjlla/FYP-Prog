"""NFR-Reliability: scheduled jobs retry, and alert once retries run out."""
from types import SimpleNamespace

import pytest

from app.tasks.reliability import retry_or_alert
from tests.conftest import auth_headers, register_and_login


class _RetryRequested(Exception):
    pass


class _FakeTask:
    """Just enough of a bound Celery task for retry_or_alert."""

    max_retries = 3

    def __init__(self, retries: int):
        self.request = SimpleNamespace(retries=retries)

    def retry(self, exc):
        raise _RetryRequested(exc)


def _notifications(client, token):
    return client.get("/kitchen/notifications", headers=auth_headers(token)).json()


def test_failure_with_retries_left_just_retries_and_alerts_nobody(client, db_session):
    manager_token = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")

    with pytest.raises(_RetryRequested):
        retry_or_alert(_FakeTask(retries=1), RuntimeError("boom"), db_session, "forecast training")

    assert _notifications(client, manager_token) == []


def test_failure_after_final_retry_alerts_manager_and_owner(client, db_session):
    manager_token = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    owner_token = register_and_login(client, email="owner@restaurant.com", role="Restaurant Owner")

    original = RuntimeError("database is on fire")
    with pytest.raises(RuntimeError) as raised:
        retry_or_alert(_FakeTask(retries=3), original, db_session, "forecast training")
    assert raised.value is original  # still recorded as a failed task

    for token in (manager_token, owner_token):
        alerts = [n for n in _notifications(client, token) if n["type"] == "job_failure"]
        assert len(alerts) == 1
        assert "forecast training" in alerts[0]["message"]
        assert "4 times" in alerts[0]["message"]
