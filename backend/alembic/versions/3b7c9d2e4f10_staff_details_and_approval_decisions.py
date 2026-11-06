"""staff contact details, and the record of approval decisions

Adds, all nullable so existing rows and the running server are unaffected:
- users: phone_number, address, emergency_contact_name, emergency_contact_phone
- purchase_orders and portion_recommendations: decided_by, decided_at,
  decision_note (who approved or rejected, when, and the reason for a rejection)

Revision ID: 3b7c9d2e4f10
Revises: e722580e43db
Create Date: 2026-11-06 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3b7c9d2e4f10'
down_revision: Union[str, None] = 'e722580e43db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone_number', sa.String(length=30), nullable=True))
    op.add_column('users', sa.Column('address', sa.String(length=300), nullable=True))
    op.add_column('users', sa.Column('emergency_contact_name', sa.String(length=150), nullable=True))
    op.add_column('users', sa.Column('emergency_contact_phone', sa.String(length=30), nullable=True))

    for table in ('purchase_orders', 'portion_recommendations'):
        op.add_column(table, sa.Column('decided_by', sa.Integer(), nullable=True))
        op.add_column(table, sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column('decision_note', sa.String(length=500), nullable=True))
        op.create_foreign_key(f'fk_{table}_decided_by_users', table, 'users', ['decided_by'], ['user_id'])

    # Decisions made before this change have no recorded time or decider. For
    # purchase orders that were approved, the approver is known.
    op.execute("UPDATE purchase_orders SET decided_by = approved_by WHERE approved_by IS NOT NULL")


def downgrade() -> None:
    for table in ('portion_recommendations', 'purchase_orders'):
        op.drop_constraint(f'fk_{table}_decided_by_users', table, type_='foreignkey')
        op.drop_column(table, 'decision_note')
        op.drop_column(table, 'decided_at')
        op.drop_column(table, 'decided_by')

    op.drop_column('users', 'emergency_contact_phone')
    op.drop_column('users', 'emergency_contact_name')
    op.drop_column('users', 'address')
    op.drop_column('users', 'phone_number')
