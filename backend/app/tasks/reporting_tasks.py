"""Celery Beat entry point for FR11.1's automated weekly summary report."""
import logging
from datetime import date, timedelta

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.reporting import NoDataForPeriodError, generate_weekly_report

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.reporting_tasks.generate_weekly_report",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_weekly_report_task(self) -> int | None:
    """Covers the 7 days ending yesterday, matching Ch4's example period
    (e.g. 2026-08-10 to 2026-08-16, generated 2026-08-17 06:00)."""
    period_end = date.today() - timedelta(days=1)
    period_start = period_end - timedelta(days=6)

    db = SessionLocal()
    try:
        report = generate_weekly_report(db, period_start=period_start, period_end=period_end)
        return report.report_id
    except NoDataForPeriodError:
        logger.info("Skipping weekly report for %s..%s — no data yet.", period_start, period_end)
        return None
    except Exception as exc:
        logger.exception("Weekly report generation failed")
        raise self.retry(exc=exc)
    finally:
        db.close()
