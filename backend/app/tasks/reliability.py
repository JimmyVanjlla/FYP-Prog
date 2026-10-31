"""Shared retry behaviour for the scheduled Celery jobs.

NFR-Reliability: scheduled tasks retry up to three times and raise an alert
if every retry fails, "rather than failing silently". Retrying alone isn't
that — after the last attempt the task used to just end up FAILED in Celery's
result backend, which nobody is watching. This sends the Restaurant Manager
and Owner a notification once the retries are exhausted.
"""
from celery import Task
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.services import notifications as notification_service

logger = get_logger(__name__)

_ALERT_ROLES = ("Restaurant Manager", "Restaurant Owner")


def retry_or_alert(task: Task, exc: Exception, db: Session, job_name: str) -> None:
    """Retries the task while attempts remain; once they're used up, alerts
    the Manager/Owner and re-raises the original error so the task is still
    recorded as failed."""
    if task.request.retries >= task.max_retries:
        logger.error("%s failed after %d attempts", job_name, task.max_retries + 1)
        try:
            db.rollback()
            for role in _ALERT_ROLES:
                notification_service.notify(
                    db,
                    recipient_role=role,
                    type_="job_failure",
                    message=(
                        f"The scheduled job '{job_name}' failed {task.max_retries + 1} times "
                        f"and has stopped retrying: {exc}"
                    ),
                )
        except Exception:
            logger.exception("Could not raise the failure alert for %s", job_name)
        raise exc
    raise task.retry(exc=exc)
