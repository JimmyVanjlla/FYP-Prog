"""Test fixtures: a fresh in-memory SQLite DB per test (fast, isolated) with
the FastAPI dependency override wired to it, plus small helpers for
registering/logging-in as a given role so tests read as scenarios rather
than HTTP boilerplate."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base_all import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def db_session():
    # StaticPool keeps a single connection alive for the whole engine, since
    # a plain in-memory sqlite DB is otherwise wiped every time a new
    # connection is checked out from the pool.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register_and_login(client: TestClient, *, email: str, role: str, password: str = "password123") -> str:
    """Returns a bearer access token for a freshly registered user."""
    client.post(
        "/auth/register",
        json={"name": "Test User", "email": email, "password": password, "role": role},
    )
    resp = client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
