
from __future__ import annotations


def test_register_success(client):
    r = client.post("/auth/register", json={
        "email": "new@example.com",
        "password": "strongpassword123"
    })
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "new@example.com"
    assert "hashed_password" not in data


def test_register_duplicate_email(client, registered_user):
    r = client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "anotherpassword123"
    })
    assert r.status_code == 409
    assert r.json()["error_code"] == "email_already_registered"


def test_login_success(client, registered_user, test_user_payload):
    r = client.post("/auth/login", json=test_user_payload)
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, registered_user):
    r = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "wrongpassword"
    })
    assert r.status_code == 401
    assert r.json()["error_code"] == "invalid_credentials"


def test_me_authenticated(client, auth_headers):
    r = client.get("/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "test@example.com"
    assert "hashed_password" not in r.json()


def test_me_unauthenticated(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_register_short_password(client):
    r = client.post("/auth/register", json={
        "email": "test2@example.com",
        "password": "short"
    })
    assert r.status_code == 422


def test_collections_crud(client, auth_headers):

    r = client.post("/collections",
        json={"name": "Test Collection", "description": "A test"},
        headers=auth_headers)
    assert r.status_code == 201
    collection_id = r.json()["id"]

    r = client.get("/collections", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r = client.get(f"/collections/{collection_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Test Collection"

    r = client.patch(f"/collections/{collection_id}",
        json={"name": "Updated Name"},
        headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Name"

    r = client.delete(f"/collections/{collection_id}", headers=auth_headers)
    assert r.status_code == 204