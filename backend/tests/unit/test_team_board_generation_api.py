"""Tests for authenticated team board generation."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.initialize import PLAYERS, TEAMS
from app.db.models import PlayerRecord, TeamRecord, UserRecord
from app.db.session import Base, get_db
from app.main import app


@pytest.fixture
def board_generation_client():
    """Provide an authenticated API client with seeded team/player data."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(UserRecord(id="user-1", email="user@example.com", password_hash="hash", first_name="Test", last_name="User"))
    session.add_all([TeamRecord(**team) for team in TEAMS])
    session.add_all([PlayerRecord(**player) for player in PLAYERS])
    session.commit()

    def override_get_db():
        """Yield the isolated test session."""
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    session.close()


def test_authenticated_user_can_generate_team_board(board_generation_client) -> None:
    """Board generation should return a persisted version identifier."""
    response = board_generation_client.post(
        "/api/teams/team-1/board/generate?draft_year=2027",
        headers={"Authorization": f"Bearer {create_access_token('user-1')}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "generated"
    assert response.json()["version"] == 1