"""
Notification creation and push dispatch — FR5.4, Ch4 §4.1 "External & Invoked
Services": "Firebase Cloud Messaging (FCM) -- a third-party push notification
service. The worker calls the FCM API to dispatch a notification; FCM then
delivers it directly to the Flutter app on the recipient's device."

Every notification is stored first (the in-app inbox reads from that), then
pushed to the recipient's registered devices if FCM is configured
(Settings.fcm_credentials_path — a real Firebase service account the
deployer has to provision). A notification that couldn't be pushed — no
credentials yet, no device registered, FCM unreachable — stays
"queued_for_retry", an honest status rather than a fake "sent", and
retry_queued_notifications() delivers it once it can be.

Routers and services only ever call notify().
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kitchen import DeviceToken, Notification
from app.models.user import User
from app.services import fcm

logger = logging.getLogger(__name__)

_TITLES = {
    "prep_update": "Prep update",
    "high_demand_alert": "High demand expected",
    "near_expiry_alert": "Ingredients nearing expiry",
    "low_stock_alert": "Low stock",
    "po_approved": "Purchase order approved",
    "po_rejected": "Purchase order rejected",
    "shift_published": "New shift",
    "job_failure": "Scheduled job failed",
}


def _dispatch_via_fcm(db: Session, notification: Notification) -> bool:
    """True if the message reached at least one of the recipient's devices."""
    if not fcm.is_configured():
        logger.info("FCM not configured — notification %s stored but not pushed.", notification.notification_id)
        return False

    tokens = list(db.scalars(select(DeviceToken).where(DeviceToken.user_id == notification.recipient_id)))
    if not tokens:
        return False

    delivered = False
    for device in tokens:
        result = fcm.send_to_token(
            device.token,
            _TITLES.get(notification.type, "Restaurant Ops"),
            notification.message,
            {"type": notification.type, "notification_id": str(notification.notification_id)},
        )
        if result == "sent":
            delivered = True
        elif result == "invalid_token":
            db.delete(device)  # the app was uninstalled or the token rotated
    return delivered


def register_device(db: Session, *, user_id: int, token: str, platform: str) -> DeviceToken:
    """FR5.4 — remembers a phone's FCM token for this user. A token already
    registered to someone else moves to this user."""
    device = db.scalars(select(DeviceToken).where(DeviceToken.token == token)).first()
    if device is None:
        device = DeviceToken(user_id=user_id, token=token, platform=platform)
        db.add(device)
    else:
        device.user_id = user_id
        device.platform = platform
        device.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(device)
    return device


def unregister_device(db: Session, *, user_id: int, token: str) -> None:
    """Called on logout so a signed-out phone stops getting that user's alerts."""
    device = db.scalars(
        select(DeviceToken).where(DeviceToken.token == token).where(DeviceToken.user_id == user_id)
    ).first()
    if device is not None:
        db.delete(device)
        db.commit()


def retry_queued_notifications(db: Session, *, max_age_hours: int = 24, limit: int = 200) -> int:
    """Pushes notifications that were stored but couldn't be delivered at the
    time (the recipient had no registered device yet, or FCM was down).
    Only recent ones — a day-old "low stock" push is noise. Returns how many
    were delivered."""
    if not fcm.is_configured():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    queued = list(
        db.scalars(
            select(Notification)
            .where(Notification.status == "queued_for_retry")
            .where(Notification.created_at >= cutoff)
            .order_by(Notification.created_at)
            .limit(limit)
        )
    )
    delivered = 0
    for notification in queued:
        if _dispatch_via_fcm(db, notification):
            notification.status = "sent"
            delivered += 1
    db.commit()
    return delivered


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
        if _dispatch_via_fcm(db, notification):
            notification.status = "sent"
        created.append(notification)

    db.commit()
    for n in created:
        db.refresh(n)
    return created
