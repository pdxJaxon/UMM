"""Tests for generating a team board from persisted records."""

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import PlayerAthleticScoreRecord, PlayerMeasurementRecord, PlayerRecord, TeamRecord
from app.db.session import Base
from app.services.team_board_service import generate_persisted_team_board


def test_persisted_board_generation_loads_player_signals() -> None:
    """Persisted players and measurements should produce a ranked team board."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(TeamRecord(id="team-1", name="Team One", city="City", abbreviation="TMO", draft_order=1, logo_url="logo", official_url="site"))
        session.add_all([
            PlayerRecord(id="p1", first_name="Top", last_name="Player", position="QB", college_id="alabama", draft_year=2027),
            PlayerRecord(id="p2", first_name="Other", last_name="Player", position="P", college_id="alabama", draft_year=2027),
        ])
        session.add(PlayerAthleticScoreRecord(player_id="p1", observed_at=datetime(2026, 9, 16), source_name="test", metric_name="pff_grade", score=95, score_scale="100"))
        session.add(PlayerMeasurementRecord(player_id="p1", observed_at=datetime(2026, 9, 16), source_name="test", height_inches=76, raw_payload={}))
        session.commit()

        board = generate_persisted_team_board(session, "team-1", 2027)

        assert len(board.entries) == 2
        assert board.entries[0].player_id == "p1"