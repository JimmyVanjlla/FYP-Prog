"""delivery deviation threshold in system config

Revision ID: e722580e43db
Revises: 99e1ef83c101
Create Date: 2026-10-31 16:11:13.955052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e722580e43db'
down_revision: Union[str, None] = '99e1ef83c101'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so the existing config row gets the old hard-coded 10%.
    op.add_column(
        "system_config",
        sa.Column("delivery_deviation_threshold", sa.Numeric(5, 2), nullable=False, server_default="10.00"),
    )


def downgrade() -> None:
    op.drop_column("system_config", "delivery_deviation_threshold")
