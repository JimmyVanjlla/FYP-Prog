"""notifications: when the recipient has seen them

Adds notifications.read_at (nullable: empty means unread), which drives the
unread count on the bell.

Revision ID: 9e4b1d6a2c57
Revises: 7a2c4f9e1b30
Create Date: 2026-11-16 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9e4b1d6a2c57'
down_revision: Union[str, None] = '7a2c4f9e1b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('notifications', sa.Column('read_at', sa.DateTime(timezone=True), nullable=True))
    # Everything raised so far counts as already seen, so the bell starts clean
    # rather than announcing a backlog of old alerts.
    op.execute("UPDATE notifications SET read_at = created_at")


def downgrade() -> None:
    op.drop_column('notifications', 'read_at')
