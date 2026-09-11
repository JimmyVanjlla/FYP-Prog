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
        "app.tasks.feedback_tasks",
        "app.tasks.reporting_tasks",
        "app.tasks.waste_tasks",
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
# analysis, waste aggregation, near-expiry batch scanning, and weekly
# report generation. (Individual WasteLog rows are also created
# event-driven off the near-expiry scan and off leftover logging itself —
# see app/tasks/inventory_tasks.py and app/services/kitchen.py — but the
# periodic WasteReductionTrend rollup below is its own scheduled job.)
celery_app.conf.beat_schedule = {
    "train-and-generate-forecasts-daily": {
        "task": "app.tasks.forecasting_tasks.train_and_generate_forecasts",
        "schedule": crontab(hour=6, minute=0),  # matches Ch4's 06:00:00 example timestamps
    },
    "check-near-expiry-batches-daily": {
        "task": "app.tasks.inventory_tasks.check_near_expiry_batches",
        "schedule": crontab(hour=5, minute=0),
    },
    "identify-high-leftover-dishes-daily": {
        "task": "app.tasks.feedback_tasks.identify_high_leftover_dishes",
        "schedule": crontab(hour=6, minute=30),  # after forecast training
    },
    "aggregate-weekly-waste-trend": {
        "task": "app.tasks.waste_tasks.aggregate_weekly_waste_trend",
        "schedule": crontab(day_of_week=1, hour=5, minute=30),  # Monday, after the near-expiry scan
    },
    "generate-weekly-report": {
        "task": "app.tasks.reporting_tasks.generate_weekly_report",
        "schedule": crontab(day_of_week=1, hour=6, minute=0),  # Monday, after the day's other runs
    },
}
