"""Celery Beat entry point for ALGORITHM CheckNearExpiryBatches (Ch4
§4.8.4 / UC-IM-08), which also feeds Module 6's waste aggregation and
FR6.4's near-expiry alerts."""
import logging

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services import notifications as notification_service
from app.services import waste as waste_service
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
        result = check_near_expiry_batches(db)

        # FR6.1/FR6.2 — expired batches become WasteLog entries.
        if result["expiry_waste_events"]:
            waste_service.record_expiry_waste(db, result["expiry_waste_events"])

        # FR6.4 — alert Inventory Staff to prioritise/discount near-expiry stock.
        if result["near_expiry_alerts"]:
            notification_service.notify(
                db,
                recipient_role="Inventory Staff",
                type_="near_expiry_alert",
                message=(
                    f"{len(result['near_expiry_alerts'])} batch(es) approaching expiry — "
                    "consider prioritising or discounting."
                ),
            )
        return result
    except Exception as exc:
        logger.exception("Near-expiry batch scan failed")
        raise self.retry(exc=exc)
    finally:
        db.close()
