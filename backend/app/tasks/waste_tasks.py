"""Celery Beat entry point for FR6.3's periodic waste-cost trend rollup.

Ch4 §4.1 lists "waste aggregation" as one of Celery Beat's five scheduled
jobs (alongside forecast training, leftover-rate analysis, near-expiry
scanning, and weekly report generation) — individual WasteLog rows are
already created automatically as leftovers/expiries happen (see
app/services/kitchen.py and app/tasks/inventory_tasks.py), but the
periodic WasteReductionTrend *rollup* FR6.3 describes ("track waste
reduction progress over time") was previously reachable only via a manual
POST /waste/trends call. This puts it on the same weekly cadence as the
report generation task, covering the same trailing 7-day window."""
import logging
from datetime import date, timedelta

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.waste import aggregate_waste_reduction_trend

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.waste_tasks.aggregate_weekly_waste_trend",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def aggregate_weekly_waste_trend_task(self) -> int:
    period_end = date.today() - timedelta(days=1)
    period_start = period_end - timedelta(days=6)

    db = SessionLocal()
    try:
        trend = aggregate_waste_reduction_trend(db, period_start=period_start, period_end=period_end)
        return trend.trend_id
    except Exception as exc:
        logger.exception("Weekly waste trend aggregation failed")
        raise self.retry(exc=exc)
    finally:
        db.close()
