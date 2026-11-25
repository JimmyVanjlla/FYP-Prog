"""orders: a status, and when each order came in

The kitchen now works through incoming orders (pending -> preparing ->
completed), and the portions of completed orders are what was actually served,
which leftover is worked out from. Every existing order is history, so it is
completed.

Revision ID: d5e9f3a72b14
Revises: c4d8e2f61a93
Create Date: 2026-11-25 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5e9f3a72b14'
down_revision: Union[str, None] = 'c4d8e2f61a93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('status', sa.String(length=20), nullable=False, server_default='completed'))
    op.add_column('orders', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'created_at')
    op.drop_column('orders', 'status')
