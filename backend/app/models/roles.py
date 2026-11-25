"""
The 3 roles the system supports, shared between the User model and the
require_role() RBAC dependency.

Originally 7 roles (Ch1 §1.5.2 / Ch4 §4.1). After the supervisor's review the
Restaurant Owner, Inventory Staff, Procurement Officer and Delivery/Logistics
Staff interfaces were removed and their duties folded into these three:

- Restaurant Manager: accounts, menu and recipes, approvals, purchasing,
  suppliers, budget, deliveries, forecasts, reports.
- Shift Supervisor: staff assignment, incoming stock and stock checks, restock
  purchase requests, waste recording.
- Kitchen Staff: the prep list, incoming orders, restock requests.

Stored as plain VARCHAR(30) on User.role per the Ch4 data dictionary, not a
DB-level enum type, so changing the roles is a data change, not a schema
migration (see the migration that moved the old roles onto these).
"""
from enum import Enum


class Role(str, Enum):
    RESTAURANT_MANAGER = "Restaurant Manager"
    KITCHEN_STAFF = "Kitchen Staff"
    SHIFT_SUPERVISOR = "Shift Supervisor"
