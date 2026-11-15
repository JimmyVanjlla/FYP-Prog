"""leftover waste logs are dated by the service day, not the day they were typed in

Revision ID: 5d1e8a7c3b92
Revises: 3b7c9d2e4f10
Create Date: 2026-11-16

Data only. A leftover's waste used to be stamped with the moment the log was
created, so leftovers entered in a batch (or a day late) all landed in the
wrong week and the weekly waste figures were empty. Re-date each leftover
waste log to midday UTC of the service day it belongs to, where that is
earlier than the day it was recorded.
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "5d1e8a7c3b92"
down_revision = "3b7c9d2e4f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT w.waste_log_id, w.logged_at, l.service_period_date "
            "FROM waste_logs w JOIN leftover_logs l ON w.source_ref_id = l.log_id "
            "WHERE w.source_type = 'leftover'"
        )
    ).all()
    updates = []
    for waste_log_id, logged_at, service_date in rows:
        if isinstance(logged_at, str):
            logged_at = datetime.fromisoformat(logged_at)
        if isinstance(service_date, str):
            service_date = datetime.fromisoformat(service_date).date()
        if logged_at.tzinfo is None:
            logged_at = logged_at.replace(tzinfo=timezone.utc)
        if service_date < logged_at.astimezone(timezone.utc).date():
            stamp = datetime(service_date.year, service_date.month, service_date.day, 12, 0, tzinfo=timezone.utc)
            updates.append({"id": waste_log_id, "stamp": stamp})
    if updates:
        bind.execute(sa.text("UPDATE waste_logs SET logged_at = :stamp WHERE waste_log_id = :id"), updates)


def downgrade() -> None:
    # The original creation times are not kept, so there is nothing to restore.
    pass
