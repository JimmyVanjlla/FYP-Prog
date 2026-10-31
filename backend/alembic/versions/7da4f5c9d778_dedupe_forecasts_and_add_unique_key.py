"""dedupe forecasts and add unique key

Training used to append a new Forecast row on every run instead of updating
the existing one for the same (menu_item_id, meal_period, forecast_date), so
running it twice doubled every forecast. This collapses existing duplicates
to the newest row per key (repointing anything that referenced an older
duplicate) and then adds the unique constraint that stops it recurring.

Revision ID: 7da4f5c9d778
Revises: d89450261840
Create Date: 2026-10-31 15:42:46.341571

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7da4f5c9d778'
down_revision: Union[str, None] = 'd89450261840'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # dup_id -> keep_id for every non-newest row in a duplicated key.
    op.execute(
        """
        CREATE TEMP TABLE _forecast_dups AS
        SELECT f.forecast_id AS dup_id, k.keep_id
        FROM forecasts f
        JOIN (
            SELECT menu_item_id, meal_period, forecast_date, MAX(forecast_id) AS keep_id
            FROM forecasts
            GROUP BY menu_item_id, meal_period, forecast_date
            HAVING COUNT(*) > 1
        ) k USING (menu_item_id, meal_period, forecast_date)
        WHERE f.forecast_id <> k.keep_id
        """
    )

    for table in ("prep_recommendations", "staffing_recommendations", "procurement_recommendations"):
        op.execute(
            f"""
            UPDATE {table} t SET forecast_id = d.keep_id
            FROM _forecast_dups d WHERE t.forecast_id = d.dup_id
            """
        )

    # forecast_accuracies.forecast_id is unique: if the surviving row already
    # has an accuracy record, drop the duplicate's; otherwise move it across.
    op.execute(
        """
        DELETE FROM forecast_accuracies a
        USING _forecast_dups d
        WHERE a.forecast_id = d.dup_id
          AND EXISTS (SELECT 1 FROM forecast_accuracies k WHERE k.forecast_id = d.keep_id)
        """
    )
    op.execute(
        """
        UPDATE forecast_accuracies a SET forecast_id = d.keep_id
        FROM _forecast_dups d WHERE a.forecast_id = d.dup_id
        """
    )

    op.execute("DELETE FROM forecasts WHERE forecast_id IN (SELECT dup_id FROM _forecast_dups)")
    op.execute("DROP TABLE _forecast_dups")

    op.create_unique_constraint(
        "uq_forecast_item_period_date", "forecasts", ["menu_item_id", "meal_period", "forecast_date"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_forecast_item_period_date", "forecasts", type_="unique")
