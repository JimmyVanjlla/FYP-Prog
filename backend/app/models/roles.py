"""
The 7 staff roles the system supports (Ch1 §1.5.2 / Ch4 §4.1), shared
between the User model and the require_role() RBAC dependency.

Stored as plain VARCHAR(30) on User.role per the Ch4 data dictionary, not a
DB-level enum type, so adding a role later is a data change, not a schema
migration.
"""
from enum import Enum


class Role(str, Enum):
    RESTAURANT_OWNER = "Restaurant Owner"
    RESTAURANT_MANAGER = "Restaurant Manager"
    KITCHEN_STAFF = "Kitchen Staff"
    INVENTORY_STAFF = "Inventory Staff"
    SHIFT_SUPERVISOR = "Shift Supervisor"
    PROCUREMENT_OFFICER = "Procurement Officer"
    DELIVERY_LOGISTICS_STAFF = "Delivery/Logistics Staff"
