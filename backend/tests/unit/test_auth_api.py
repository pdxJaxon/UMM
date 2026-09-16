"""Tests for database-backed registration, login, and bearer authentication."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app


@pytest.fixture
def auth_client():
    """Provide an isolated database-backed API client."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    def override_get_db():
        """Yield the isolated authentication database session."""
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), session
    app.dependency_overrides.clear()
    session.close()


def test_register_and_login_return_access_token(auth_client) -> None:
    """Registration and login should return usable bearer tokens."""
    client, _ = auth_client
    payload = {
        "email": "new.user@example.com",
        "password": "StrongP@ssw0rd!",
        "first_name": "New",
        "last_name": "User",
    }

    registered = client.post("/auth/register", json=payload)
    logged_in = client.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})

    assert registered.status_code == 201
    assert registered.json()["token_type"] == "bearer"
    assert logged_in.status_code == 200
    assert logged_in.json()["access_token"]


def test_duplicate_registration_and_invalid_login_are_rejected(auth_client) -> None:
    """Existing emails and incorrect passwords must not authenticate."""
    client, _ = auth_client
    payload = {
        "email": "duplicate@example.com",
        "password": "StrongP@ssw0rd!",
        "first_name": "Duplicate",
        "last_name": "User",
    }

    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409
    assert client.post(
        "/auth/login",
        json={"email": payload["email"], "password": "incorrect-password"},
    ).status_code == 401


def test_draft_requires_bearer_auth(auth_client) -> None:
    """Protected draft endpoints must reject anonymous requests."""
    client, _ = auth_client

    response = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-1", "draft_year": 2026},
    )

    assert response.status_code == 401
