"""Tests for versioned team board generation."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.services.team_board_service import generate_team_board, get_latest_team_board


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