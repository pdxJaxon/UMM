"""Tests for the team board retrieval endpoint."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import CollegeRecord, PlayerRecord, TeamBoardEntryRecord, TeamBoardRecord
from app.db.session import Base, get_db
from app.main import app


def test_team_board_endpoint_returns_empty_state_when_unbuilt() -> None:
    """The board endpoint should report an ungenerated board cleanly."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)

    def override_get_db():
        """Yield the isolated test session."""
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get("/api/teams/team-1/board?draft_year=2027")
        assert response.status_code == 200
        assert response.json()["board"] is None
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_team_board_endpoint_includes_player_details() -> None:
    """The board payload should carry player info needed to render each row."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        CollegeRecord(
            id="alabama",
            name="Alabama",
            abbreviation="ALA",
            conference="SEC",
            division="FBS",
            logo_url="logo",
            official_url="site",
        )
    )
    session.add(PlayerRecord(id="p-1", first_name="Tua", last_name="Tagovailoa", position="QB", college_id="alabama", draft_year=2027))
    board = TeamBoardRecord(
        id=1,
        team_id="team-1",
        draft_year=2027,
        board_type="default",
        version=1,
        generated_at=datetime.now(UTC),
        scoring_version="test",
        scoring_weights={},
    )
    session.add(board)
    session.add(TeamBoardEntryRecord(board_id=1, player_id="p-1", rank_position=1, score=92.5, score_breakdown={"need": 80, "fit": 70}))
    session.commit()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get("/api/teams/team-1/board?draft_year=2027")
        assert response.status_code == 200
        payload = response.json()["entries"][0]
        assert payload["first_name"] == "Tua"
        assert payload["last_name"] == "Tagovailoa"
        assert payload["position"] == "QB"
        assert payload["college_name"] == "Alabama"
    finally:
        app.dependency_overrides.clear()
        session.close()