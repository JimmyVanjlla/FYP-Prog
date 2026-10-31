"""prep recommendation forecast date

Revision ID: 21967ddc190d
Revises: 1a85eacb1fc0
Create Date: 2026-10-31 15:57:50.564794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21967ddc190d'
down_revision: Union[str, None] = '1a85eacb1fc0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prep_recommendations", sa.Column("forecast_date", sa.Date(), nullable=True))
    # Forecast-backed rows can recover their date from the forecast they point at.
    op.execute(
        """
        UPDATE prep_recommendations p SET forecast_date = f.forecast_date
        FROM forecasts f WHERE p.forecast_id = f.forecast_id
        """
    )


def downgrade() -> None:
    op.drop_column("prep_recommendations", "forecast_date")
