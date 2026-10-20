"""Tests for versioned team board generation."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
import pytest

from app.services.team_board_service import copy_board_for_user, generate_team_board, get_latest_board, get_latest_team_board


def test_generate_team_board_ranks_candidates_and_versions_boards() -> None:
    """Candidates should be ranked by explainable score and versions incremented."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    candidates = [
        {"id": "player-low", "position": "P", "ranking_values": {"pff": 40}},
        {"id": "player-high", "position": "QB", "ranking_values": {"pff": 90}, "team_needs": [{"position_code": "QB", "need_score": 100}]},
    ]

    with Session(engine) as session:
        first = generate_team_board(session, "team-1", 2027, candidates)
        second = generate_team_board(session, "team-1", 2027, candidates)

        assert first.version == 1
        assert second.version == 2
        latest = get_latest_team_board(session, "team-1", 2027)
        assert latest.id == second.id
        assert latest.entries[0].player_id == "player-high"
        assert "player_evaluation" in latest.entries[0].score_breakdown


def test_get_latest_board_can_return_personal_board() -> None:
    """Personal boards should be retrievable independently from default boards."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    candidates = [{"id": "player-1", "position": "QB", "ranking_values": {"pff": 90}}]

    with Session(engine) as session:
        generate_team_board(session, "team-1", 2027, candidates)
        personal = generate_team_board(session, "team-1", 2027, candidates, board_type="personal", user_id="user-1")

        latest = get_latest_board(session, "team-1", 2027, board_type="personal", user_id="user-1")

        assert latest is not None
        assert latest.id == personal.id
        assert latest.board_type == "personal"


def test_copy_ignores_inactive_entries_and_rejects_empty_or_personal_sources():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = generate_team_board(session, "team-1", 2027, [
            {"id": "inactive", "position": "QB", "ranking_values": {"pff": 90}},
            {"id": "active", "position": "WR", "ranking_values": {"pff": 80}},
        ])
        source.entries[0].is_active = False
        session.commit()
        copied = copy_board_for_user(session, source, "user")
        assert [(entry.player_id, entry.rank_position) for entry in copied.entries] == [("active", 1)]
        with pytest.raises(ValueError, match="Only a default"):
            copy_board_for_user(session, copied, "other-user")
        source.entries[1].is_active = False
        session.commit()
        with pytest.raises(ValueError, match="no active prospects"):
            copy_board_for_user(session, source, "user")
        assert session.query(type(source)).count() == 2