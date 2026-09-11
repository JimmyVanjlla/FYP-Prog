"""Celery Beat entry point for ALGORITHM CheckNearExpiryBatches (Ch4
§4.8.4 / UC-IM-08)."""
import logging

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.inventory import check_near_expiry_batches

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.inventory_tasks.check_near_expiry_batches",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def check_near_expiry_batches_task(self) -> dict:
    db = SessionLocal()
    try:
        return check_near_expiry_batches(db)
    except Exception as exc:
        logger.exception("Near-expiry batch scan failed")
        raise self.retry(exc=exc)
    finally:
        db.close()
