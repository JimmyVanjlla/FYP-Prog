"""Celery Beat entry point that re-attempts push delivery for notifications
that were stored but couldn't be pushed when created (FR5.4)."""
import logging

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.notifications import retry_queued_notifications
from app.tasks.reliability import retry_or_alert

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.notification_tasks.retry_queued_notifications",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def retry_queued_notifications_task(self) -> int:
    db = SessionLocal()
    try:
        return retry_queued_notifications(db)
    except Exception as exc:
        logger.exception("Queued notification retry failed")
        retry_or_alert(self, exc, db, "push notification retry")
    finally:
        db.close()
