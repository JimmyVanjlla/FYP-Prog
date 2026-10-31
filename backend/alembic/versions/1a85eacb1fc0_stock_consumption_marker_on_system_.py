"""stock consumption marker on system config

Revision ID: 1a85eacb1fc0
Revises: 7da4f5c9d778
Create Date: 2026-10-31 15:45:15.114611

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a85eacb1fc0'
down_revision: Union[str, None] = '7da4f5c9d778'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("system_config", sa.Column("stock_consumption_applied_through", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("system_config", "stock_consumption_applied_through")
