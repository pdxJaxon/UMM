"""Tests for the NFL team reference-data endpoint."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.initialize import seed_reference_data
from app.db.models import TeamNeedRecord
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
    assert teams[7]["abbreviation"] == "CLE"
    assert teams[7]["randomness_score"] == 85


def test_team_needs_endpoint_returns_active_needs_in_priority_order(teams_client) -> None:
    """The board can render the active needs in descending priority order."""
    session = next(teams_client.app.dependency_overrides[get_db]())
    session.add_all([
        TeamNeedRecord(
            team_id="team-1", draft_year=2027, position_code="QB",
            role_level="starter", need_score=80, source_name="test",
            observed_at=datetime(2026, 10, 1),
        ),
        TeamNeedRecord(
            team_id="team-1", draft_year=2027, position_code="WR",
            role_level="starter", need_score=90, source_name="test",
            observed_at=datetime(2026, 10, 1),
        ),
        TeamNeedRecord(
            team_id="team-1", draft_year=2027, position_code="RB",
            role_level="starter", need_score=0, source_name="test",
            observed_at=datetime(2026, 10, 1),
        ),
        TeamNeedRecord(
            team_id="team-1", draft_year=2027, position_code="TE",
            role_level="starter", need_score=100, source_name="test",
            observed_at=datetime(2026, 10, 1), is_active=False,
        ),
    ])
    session.commit()

    response = teams_client.get("/api/teams/team-1/needs?draft_year=2027")

    assert response.status_code == 200
    assert [need["position_code"] for need in response.json()] == ["WR", "QB", "RB"]
