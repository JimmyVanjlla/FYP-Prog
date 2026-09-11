"""
Background Processing Tier — Celery app, Redis as broker/result backend
(Ch4 §4.1). Celery was chosen over APScheduler for distributed workers,
persistent queues, and retry-on-failure (Ch2 §2.1.4); Redis over RabbitMQ
for lower operational complexity (Ch2 §2.1.4).

Run a worker with:  celery -A app.celery_app worker --loglevel=info --pool=solo
Run the beat scheduler with:  celery -A app.celery_app beat --loglevel=info
(--pool=solo is a Windows-only requirement; drop it on Linux/the deployed
Railway/Render worker.)
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "restaurant_ops",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.forecasting_tasks",
        "app.tasks.inventory_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # NFR-Reliability: retry scheduled tasks up to 3 times, alert rather
    # than fail silently if all retries are exhausted.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Ch4 §4.1 — Celery Beat triggers: Prophet forecast training, leftover-rate
# analysis (Sprint 3), waste aggregation (Sprint 3), near-expiry batch
# scanning, and weekly report generation (Sprint 5). Only the two wired up
# in this sprint are scheduled here; later sprints add their own entries.
celery_app.conf.beat_schedule = {
    "train-and-generate-forecasts-daily": {
        "task": "app.tasks.forecasting_tasks.train_and_generate_forecasts",
        "schedule": crontab(hour=6, minute=0),  # matches Ch4's 06:00:00 example timestamps
    },
    "check-near-expiry-batches-daily": {
        "task": "app.tasks.inventory_tasks.check_near_expiry_batches",
        "schedule": crontab(hour=5, minute=0),
    },
}
