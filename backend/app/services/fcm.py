"""
Firebase Cloud Messaging delivery over the HTTP v1 API (FR5.4, Ch4 §4.1).

Talks to FCM directly with a service-account access token rather than the
firebase-admin SDK, which would pull in a large tree of Google client
libraries to do one HTTP POST. Nothing here runs unless
Settings.fcm_credentials_path points at a service-account JSON file — until
then notifications are stored and shown in-app but not pushed.
"""
import json
from typing import Literal

import requests

from app.core.config import get_settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

SendResult = Literal["sent", "invalid_token", "error"]

_credentials = None
_project_id: str | None = None


def is_configured() -> bool:
    return bool(get_settings().fcm_credentials_path)


def _access_token() -> tuple[str, str]:
    """(access token, firebase project id), refreshing the cached
    credentials when they've expired."""
    global _credentials, _project_id
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    path = get_settings().fcm_credentials_path
    if _credentials is None:
        _credentials = service_account.Credentials.from_service_account_file(path, scopes=_SCOPES)
        with open(path, encoding="utf-8") as f:
            _project_id = json.load(f)["project_id"]
    if not _credentials.valid:
        _credentials.refresh(Request())
    return _credentials.token, _project_id or ""


def send_to_token(token: str, title: str, body: str, data: dict[str, str] | None = None) -> SendResult:
    """Pushes one message to one device. `invalid_token` means FCM no longer
    recognises the token (app uninstalled / token rotated) and it should be
    dropped; `error` is anything transient worth retrying later."""
    try:
        access_token, project_id = _access_token()
        response = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={
                "message": {
                    "token": token,
                    "notification": {"title": title, "body": body},
                    "data": data or {},
                }
            },
            timeout=10,
        )
    except Exception:
        logger.exception("FCM request failed")
        return "error"

    if response.status_code == 200:
        return "sent"
    if response.status_code in (400, 404) and any(
        marker in response.text for marker in ("UNREGISTERED", "INVALID_ARGUMENT", "NOT_FOUND")
    ):
        return "invalid_token"
    logger.warning("FCM rejected a message: %s %s", response.status_code, response.text[:200])
    return "error"
