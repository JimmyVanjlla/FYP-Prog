"""restock decisions, deleted staff, meal periods per dish, leftover percentages

Adds, all nullable or with a default so existing rows and the running server
are unaffected:
- restocking_requests: decided_by, decided_at, decision_note
- users: deleted_at, purged_at (soft delete, recoverable for 60 days)
- menu_items: meal_periods (default "Lunch,Dinner", what every dish served so far)
- leftover_logs: meal_period, leftover_percent

Revision ID: 7a2c4f9e1b30
Revises: 5d1e8a7c3b92
Create Date: 2026-11-16 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7a2c4f9e1b30'
down_revision: Union[str, None] = '5d1e8a7c3b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('restocking_requests', sa.Column('decided_by', sa.Integer(), nullable=True))
    op.add_column('restocking_requests', sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('restocking_requests', sa.Column('decision_note', sa.String(length=500), nullable=True))
    op.create_foreign_key(
        'fk_restocking_requests_decided_by_users', 'restocking_requests', 'users', ['decided_by'], ['user_id']
    )

    op.add_column('users', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('purged_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        'menu_items',
        sa.Column('meal_periods', sa.String(length=60), server_default='Lunch,Dinner', nullable=False),
    )

    op.add_column('leftover_logs', sa.Column('meal_period', sa.String(length=20), nullable=True))
    op.add_column('leftover_logs', sa.Column('leftover_percent', sa.Integer(), nullable=True))

    # A request that was declined before this change has no recorded reason.
    # Nothing to back-fill: the new columns stay empty for old decisions.


def downgrade() -> None:
    op.drop_column('leftover_logs', 'leftover_percent')
    op.drop_column('leftover_logs', 'meal_period')
    op.drop_column('menu_items', 'meal_periods')
    op.drop_column('users', 'purged_at')
    op.drop_column('users', 'deleted_at')
    op.drop_constraint('fk_restocking_requests_decided_by_users', 'restocking_requests', type_='foreignkey')
    op.drop_column('restocking_requests', 'decision_note')
    op.drop_column('restocking_requests', 'decided_at')
    op.drop_column('restocking_requests', 'decided_by')
