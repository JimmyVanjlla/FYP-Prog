"""
Push notification dispatch — FR5.4, Ch4 §4.1 "External & Invoked Services":
"Firebase Cloud Messaging (FCM) -- a third-party push notification service.
The worker calls the FCM API to dispatch a notification; FCM then delivers
it directly to the Flutter app on the recipient's device."

No FCM service account is configured yet (that's a real external
credential the user has to provision, same as Supabase/Redis were) — see
Settings.fcm_credentials_path. Until it is, this stores every Notification
row honestly as "queued_for_retry" rather than faking a "sent" status, so
the Notification table stays truthful about what actually reached a
device. Swap _dispatch_via_fcm's body for a real firebase-admin call once
credentials exist; nothing else in the codebase needs to change — routers
and services only ever call notify().
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.kitchen import Notification
from app.models.user import User

logger = logging.getLogger(__name__)


def _dispatch_via_fcm(notification: Notification) -> bool:
    settings = get_settings()
    if not settings.fcm_credentials_path:
        logger.info(
            "FCM not configured (Settings.fcm_credentials_path unset) — "
            "notification %s stored but not delivered.",
            notification.notification_id,
        )
        return False
    # Real dispatch would go here, e.g. via the `firebase-admin` SDK,
    # once settings.fcm_credentials_path points at a real service account.
    return False


def notify(
    db: Session, *, type_: str, message: str, recipient_role: str | None = None, recipient_id: int | None = None
) -> list[Notification]:
    """FR5.4. Pass either recipient_role (fans out to every active user
    with that role — e.g. all Kitchen Staff) or a specific recipient_id."""
    if recipient_id is not None:
        recipient_ids = [recipient_id]
    elif recipient_role is not None:
        recipient_ids = list(
            db.scalars(
                select(User.user_id).where(User.role == recipient_role).where(User.is_active.is_(True))
            )
        )
    else:
        raise ValueError("notify() requires either recipient_role or recipient_id")

    created: list[Notification] = []
    for uid in recipient_ids:
        notification = Notification(recipient_id=uid, type=type_, message=message, status="queued_for_retry")
        db.add(notification)
        db.flush()
        if _dispatch_via_fcm(notification):
            notification.status = "sent"
        created.append(notification)

    db.commit()
    for n in created:
        db.refresh(n)
    return created
