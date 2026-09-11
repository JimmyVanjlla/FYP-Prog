"""Celery Beat entry point for Algorithm 1 (Ch4 §4.8.1). Runs daily
(see app/celery_app.py's beat_schedule) — "Celery Beat triggers scheduled
jobs... Prophet forecast training" (Ch4 §4.1)."""
import logging

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.forecasting import train_and_generate_forecasts

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.forecasting_tasks.train_and_generate_forecasts",
    bind=True,
    max_retries=3,  # NFR-Reliability
    default_retry_delay=60,
)
def train_and_generate_forecasts_task(self) -> dict:
    db = SessionLocal()
    try:
        return train_and_generate_forecasts(db)
    except Exception as exc:
        logger.exception("Forecast training run failed")
        raise self.retry(exc=exc)
    finally:
        db.close()
