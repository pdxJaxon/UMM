"""Tests for the college reference-data endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.initialize import seed_reference_data
from app.db.session import Base, get_db
from app.main import app


@pytest.fixture
def colleges_client():
    """Provide an isolated seeded college database to the API client."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_reference_data(session)

    def override_get_db():
        """Yield the isolated database session."""
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    session.close()


def test_list_colleges_returns_conference_and_division_metadata(colleges_client) -> None:
    """The endpoint should expose existing FBS programs plus the reviewed FCS school."""
    response = colleges_client.get("/api/colleges")

    assert response.status_code == 200
    colleges = response.json()
    assert len(colleges) == 137
    assert {college["division"] for college in colleges} == {"FBS", "FCS"}
    assert {college["conference"] for college in colleges} >= {"ACC", "Big Ten", "SEC"}
    assert all(college["logo_url"].startswith("https://") for college in colleges if college["division"] == "FBS")
    youngstown = next(college for college in colleges if college["id"] == "youngstown-state")
    assert youngstown["division"] == "FCS"
    assert youngstown["official_url"] == "https://ysusports.com/sports/football"