"""
tests/conftest.py

Shared pytest fixtures for the entire test suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aletheia_core.db.base import Base, get_db
from aletheia_core.config import get_settings


# --- Test database (SQLite in-memory for unit/integration tests) ----------

TEST_DATABASE_URL = "sqlite:///./test.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="function")
def db():
    """
    Fresh database session per test function.
    Creates all tables before the test, drops them after.
    """
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db):
    """
    FastAPI TestClient with the test DB injected via dependency override.
    Overrides get_db() so routes use the test session.
    """

    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/api-gateway"))

    from app.main import create_app

    app = create_app()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c


@pytest.fixture
def test_user_payload():
    return {"email": "test@example.com", "password": "testpassword123"}


@pytest.fixture
def registered_user(client, test_user_payload):
    """Register a user and return the response."""
    response = client.post("/auth/register", json=test_user_payload)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def auth_headers(client, test_user_payload, registered_user):
    """Return Authorization headers for an authenticated user."""
    response = client.post("/auth/login", json=test_user_payload)
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}