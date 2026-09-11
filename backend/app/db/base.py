from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base every SQLAlchemy model inherits from.

    Alembic's env.py imports Base.metadata (via app.db.base_all, which pulls
    in every model module) to autogenerate migrations."""
