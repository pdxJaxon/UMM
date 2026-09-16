"""Tests for the NFL team reference-data endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.initialize import seed_reference_data
from app.db.session import Base, get_db
from app.main import app


@pytest.fixture
def teams_client():
    """Provide a team API client backed by an isolated seeded database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_reference_data(session)

    def override_get_db():
        """Yield the test database session to FastAPI."""
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    session.close()


def test_list_teams_returns_all_nfl_teams_with_assets(teams_client) -> None:
    """The endpoint should return all seeded teams and their display metadata."""
    response = teams_client.get("/api/teams")

    assert response.status_code == 200
    teams = response.json()
    assert len(teams) == 32
    assert teams[0]["abbreviation"] == "ARI"
    assert teams[-1]["abbreviation"] == "WSH"
    assert teams[0]["logo_url"].startswith("https://")
    assert teams[0]["official_url"].startswith("https://www.nfl.com/")
