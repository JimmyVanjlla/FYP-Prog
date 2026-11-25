"""orders: whether the end-of-day count has taken them off stock

The end-of-day button counts completed orders one by one as they are completed,
so it marks each order it has counted. The nightly job skips those, so nothing is
counted twice. Every existing order is not yet counted (the nightly clock already
covers whole past days).

Revision ID: e6f1a4b83c25
Revises: d5e9f3a72b14
Create Date: 2026-11-26 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e6f1a4b83c25'
down_revision: Union[str, None] = 'd5e9f3a72b14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('stock_counted', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('orders', 'stock_counted')
