"""Tests for franchise and current-regime tendency blending."""

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import TeamDraftingTendencyRecord, TeamLeadershipRecord, TeamRecord
from app.db.initialize import TEAMS
from app.db.session import Base
from app.services.leadership_tendencies import get_effective_tendencies


def test_gm_tendency_follows_the_gm_to_a_new_team_and_blends_with_franchise_history() -> None:
    """A current team's effective tendency should include its GM's prior team history."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all(TeamRecord(**team) for team in TEAMS[:3])
    session.add_all([
        TeamDraftingTendencyRecord(
            team_id="team-3", draft_year=None, tendency_type="trade_up",
            preference_score=20, confidence_score=100, sample_size=10,
            source_name="historical-trade-analysis", observed_at=datetime.now(UTC),
        ),
        TeamDraftingTendencyRecord(
            team_id="team-1", draft_year=None, actor_type="gm", actor_id="gm-a", actor_name="GM A",
            tendency_type="trade_up", preference_score=100, confidence_score=100, sample_size=4,
            source_name="historical-trade-analysis", observed_at=datetime.now(UTC),
        ),
        TeamLeadershipRecord(
            team_id="team-3", role_type="gm", person_id="gm-a", person_name="GM A",
            start_year=2025, source_name="leadership-source", observed_at=datetime.now(UTC),
        ),
    ])
    session.commit()

    tendencies = get_effective_tendencies(session, "team-3", 2026)
    trade_up = next(tendency for tendency in tendencies if tendency["tendency_type"] == "trade_up")

    assert trade_up["scope"] == "franchise-plus-regime"
    assert trade_up["preference_score"] == 43.53
    assert {component["actor_id"] for component in trade_up["components"]} == {None, "gm-a"}