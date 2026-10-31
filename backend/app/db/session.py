from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# check_same_thread is only needed for the sqlite dev fallback.
#
# prepare_threshold=None turns off psycopg 3's automatic prepared statements.
# Supabase's transaction pooler (the IPv4 URL this project must use) gives each
# transaction a different server connection, so a statement prepared on one
# connection is "already exists" or "does not exist" on the next: an
# intermittent DuplicatePreparedStatement that only appears once a query has
# run a few times.
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
else:
    _connect_args = {"prepare_threshold": None}

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
