"""
Imports every SQLAlchemy model so Base.metadata is fully populated before
Alembic autogenerates a migration or a test spins up an in-memory schema.

Add the import here whenever a new model module is added in a later sprint —
nothing else needs to change for Alembic to pick it up.
"""
from app.db.base import Base  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.menu import MenuItem, RecipeIngredientLink  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
