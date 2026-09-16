"""Contract-level tests for the mock draft lifecycle."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.initialize import PLAYERS, TEAMS
from app.db.models import PlayerRecord, TeamRecord, UserRecord
from app.db.session import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def isolate_draft_store() -> None:
    """Provide an isolated relational database before each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all(
        [
            UserRecord(
                id="user-1",
                email="user-1@example.com",
                password_hash="hash",
                first_name="Test",
                last_name="User",
            ),
            UserRecord(
                id="owner",
                email="owner@example.com",
                password_hash="hash",
                first_name="Draft",
                last_name="Owner",
            ),
        ]
    )
    session.add_all([TeamRecord(**team) for team in TEAMS])
    session.add_all([PlayerRecord(**player) for player in PLAYERS])
    session.commit()

    def override_get_db():
        """Yield the isolated test session to FastAPI."""
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    session.close()


def test_controlled_team_flow_auto_simulates_other_teams() -> None:
    """The server should auto-pick team one before team two's user pick."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}

    response = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-2", "draft_year": 2026},
        headers=headers,
    )
    assert response.status_code == 201
    draft_id = response.json()["draft_run_id"]

    response = client.post(f"/api/drafts/{draft_id}/auto-simulate", headers=headers)
    assert response.status_code == 200
    state = response.json()
    assert state["current_team_id"] == "team-2"
    assert state["picks"][0]["team_id"] == "team-1"
    assert state["picks"][0]["selection_source"] == "AUTO"

    response = client.post(
        f"/api/drafts/{draft_id}/picks",
        json={"team_id": "team-2", "player_id": "player-2"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["picks"][1]["selection_source"] == "USER"


def test_draft_access_is_limited_to_owner() -> None:
    """A different user must not read another user's draft."""
    client = TestClient(app)
    response = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-1", "draft_year": 2026},
        headers={"Authorization": f"Bearer {create_access_token('owner')}"},
    )
    draft_id = response.json()["draft_run_id"]

    response = client.get(
        f"/api/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {create_access_token('user-1')}"},
    )

    assert response.status_code == 403


def test_duplicate_player_selection_is_rejected() -> None:
    """A player cannot be selected more than once in one draft."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}
    draft_id = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-1", "draft_year": 2026},
        headers=headers,
    ).json()["draft_run_id"]

    first = client.post(
        f"/api/drafts/{draft_id}/picks",
        json={"team_id": "team-1", "player_id": "player-1"},
        headers=headers,
    )
    duplicate = client.post(
        f"/api/drafts/{draft_id}/picks",
        json={"team_id": "team-1", "player_id": "player-1"},
        headers=headers,
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
