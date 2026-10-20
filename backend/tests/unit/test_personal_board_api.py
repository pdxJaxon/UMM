"""Tests for user-owned board copies and ordering."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.models import CollegeRecord, PlayerRecord, TeamBoardEntryRecord, TeamBoardRecord, TeamRecord, UserRecord
from app.db.session import Base, get_db
from app.main import app


def test_user_can_copy_and_reorder_personal_board() -> None:
    """A user should copy a default board and save a complete new order."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(UserRecord(id="user-1", email="user@example.com", password_hash="hash", first_name="Test", last_name="User"))
    session.add(UserRecord(id="user-2", email="other@example.test", password_hash="hash", first_name="Other", last_name="User"))
    session.add(TeamRecord(id="team-1", name="Team One", city="City", abbreviation="TMO", draft_order=1, logo_url="logo", official_url="site"))
    session.add(CollegeRecord(id="alabama", name="Alabama", abbreviation="ALA", conference="SEC", division="FBS", logo_url="logo", official_url="site"))
    session.add_all([
        PlayerRecord(id="p1", first_name="Alpha", last_name="One", position="QB", college_id="alabama", draft_year=2027),
        PlayerRecord(id="p2", first_name="Beta", last_name="Two", position="WR", college_id="alabama", draft_year=2027),
    ])
    session.commit()
    board = TeamBoardRecord(team_id="team-1", draft_year=2027, board_type="default", version=1, generated_at=datetime.now(UTC), scoring_version="test", scoring_weights={})
    session.add(board)
    session.flush()
    session.add_all([
        TeamBoardEntryRecord(board_id=board.id, player_id="p1", rank_position=1, score=90, score_breakdown={}),
        TeamBoardEntryRecord(board_id=board.id, player_id="p2", rank_position=2, score=80, score_breakdown={}),
    ])
    session.commit()

    def override_get_db():
        """Yield the isolated board database."""
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}
        copied = client.post("/api/teams/team-1/board/copy?draft_year=2027", headers=headers)
        assert copied.status_code == 200
        board_id = copied.json()["board_id"]

        reordered = client.put(
            f"/api/teams/team-1/board/{board_id}/order",
            headers=headers,
            json={"player_ids": ["p2", "p1"]},
        )
        assert reordered.status_code == 200
        assert reordered.json()["version"] == 2

        personal = client.get(
            "/api/teams/team-1/board?draft_year=2027&board_type=personal",
            headers=headers,
        )
        assert personal.status_code == 200
        assert personal.json()["board"]["id"] == board_id
        assert personal.json()["entries"][0]["player_id"] == "p2"
        assert client.post("/api/teams/team-1/board/copy?draft_year=2027").status_code == 401
        conflict = client.post("/api/teams/team-1/board/copy?draft_year=2027", headers=headers)
        assert conflict.status_code == 409
        assert session.query(TeamBoardRecord).count() == 2
        replaced = client.post(
            "/api/teams/team-1/board/copy?draft_year=2027&replace_existing=true", headers=headers,
        )
        assert replaced.status_code == 200
        assert replaced.json()["version"] == 3
        assert replaced.json()["board_id"] != board_id
        latest = client.get(
            "/api/teams/team-1/board?draft_year=2027&board_type=personal", headers=headers,
        ).json()
        assert latest["board"]["id"] == replaced.json()["board_id"]
        assert [entry["player_id"] for entry in latest["entries"]] == ["p1", "p2"]
        # Replaced copies remain intact as history, not as the active personal board.
        assert session.get(TeamBoardRecord, board_id).version == 2
        assert sorted(session.get(TeamBoardRecord, board_id).entries, key=lambda entry: entry.rank_position)[0].player_id == "p2"
        other_headers = {"Authorization": f"Bearer {create_access_token('user-2')}"}
        other = client.get(
            "/api/teams/team-1/board?draft_year=2027&board_type=personal", headers=other_headers,
        )
        assert other.json()["board"] is None
        assert client.put(
            f"/api/teams/team-1/board/{replaced.json()['board_id']}/order",
            headers=other_headers, json={"player_ids": ["p2", "p1"]},
        ).status_code == 404
        assert client.post(
            "/api/teams/team-1/board/copy?draft_year=2027", headers=other_headers,
        ).json()["version"] == 1
        assert client.get(
            "/api/teams/team-1/board?draft_year=2027",
        ).json()["entries"][0]["player_id"] == "p1"
        before_count = session.query(TeamBoardRecord).count()
        for entry in board.entries:
            entry.is_active = False
        session.commit()
        assert client.post(
            "/api/teams/team-1/board/copy?draft_year=2027&replace_existing=true", headers=headers,
        ).status_code == 400
        assert session.query(TeamBoardRecord).count() == before_count
        assert client.post(
            "/api/teams/team-2/board/copy?draft_year=2027", headers=headers,
        ).status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()