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
from app.main import create_app  # works because pyproject.toml pythonpath includes services/api-gateway

TEST_DATABASE_URL = "sqlite:///./test.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db):
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
    response = client.post("/auth/register", json=test_user_payload)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def auth_headers(client, test_user_payload, registered_user):
    response = client.post("/auth/login", json=test_user_payload)
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}