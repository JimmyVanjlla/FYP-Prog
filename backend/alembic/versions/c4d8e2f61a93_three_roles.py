"""three roles: Manager, Shift Supervisor, Kitchen Staff

After the supervisor's review the Restaurant Owner, Inventory Staff,
Procurement Officer and Delivery/Logistics Staff interfaces were removed.
Existing accounts are moved to the role that now holds their duties:

  Restaurant Owner         -> Restaurant Manager
  Inventory Staff          -> Shift Supervisor
  Procurement Officer      -> Shift Supervisor
  Delivery/Logistics Staff -> Kitchen Staff

The four demo logins for the removed roles are then deactivated and deleted
(they appear in the Deleted tab for 60 days and can be restored), so the staff
list is left with the people who still have a job in the system. Nothing they
did is lost: the rows stay, so approvals and audit entries still point at them.

Revision ID: c4d8e2f61a93
Revises: 9e4b1d6a2c57
Create Date: 2026-11-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4d8e2f61a93'
down_revision: Union[str, None] = '9e4b1d6a2c57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    # The demo logins are matched by their old role as well, so a real person who
    # happens to have one of these addresses with a different role is untouched.
    op.execute(
        "UPDATE users SET is_active = FALSE, deleted_at = CURRENT_TIMESTAMP "
        "WHERE deleted_at IS NULL AND email IN ('owner@test.com', 'inventory@test.com', "
        "'procurement@test.com', 'delivery@test.com') "
        "AND role IN ('Restaurant Owner', 'Inventory Staff', 'Procurement Officer', 'Delivery/Logistics Staff')"
    )
    op.execute("UPDATE users SET role = 'Restaurant Manager' WHERE role = 'Restaurant Owner'")
    op.execute("UPDATE users SET role = 'Shift Supervisor' WHERE role IN ('Inventory Staff', 'Procurement Officer')")
    op.execute("UPDATE users SET role = 'Kitchen Staff' WHERE role = 'Delivery/Logistics Staff'")


def downgrade() -> None:
    # The old roles cannot be told apart from the new ones afterwards, so there is
    # nothing to restore; the accounts keep the role they were moved to.
    pass
