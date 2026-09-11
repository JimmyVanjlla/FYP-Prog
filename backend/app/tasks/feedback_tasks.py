"""Celery Beat entry point for ALGORITHM IdentifyHighLeftoverDishes (Ch4
§4.8.2)."""
import logging

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.feedback import identify_high_leftover_dishes

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.feedback_tasks.identify_high_leftover_dishes",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def identify_high_leftover_dishes_task(self) -> int:
    db = SessionLocal()
    try:
        flagged = identify_high_leftover_dishes(db)
        return len(flagged)
    except Exception as exc:
        logger.exception("Leftover-rate analysis run failed")
        raise self.retry(exc=exc)
    finally:
        db.close()
