from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# check_same_thread is only needed for the sqlite dev fallback; ignored by
# psycopg for real Postgres connections.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """FastAPI dependency: yields a request-scoped DB session and always
    closes it, even if the request handler raises."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
