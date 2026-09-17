"""Tests for multi-source weekly prospect refreshes."""

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import PlayerMeasurementRecord, PlayerRecord
from app.db.session import Base
from app.services.prospect_refresh import CompositeProspectProvider, run_weekly_prospect_refresh


class StaticProvider:
    """Small normalized provider fixture."""

    def __init__(self, records: list[dict[str, object]]) -> None:
        """Store records returned by this source."""
        self.records = records

    def fetch(self, draft_year: int) -> list[dict[str, object]]:
        """Return normalized records for a draft year."""
        return self.records


def test_composite_provider_merges_sources_by_player_id() -> None:
    """PFF-style ranking data should enrich an nflverse-style profile."""
    provider = CompositeProspectProvider(
        [
            StaticProvider([{"id": "p1", "first_name": "Test", "position": "WR", "college_id": "alabama", "measurements": {"height_inches": 76}}]),
            StaticProvider([{"id": "p1", "last_name": "Prospect", "measurements": {"weight_lbs": 210}, "athletic_scores": [{"source_name": "pff", "metric_name": "grade", "score": 90}]}]),
        ]
    )

    result = provider.fetch(2027)

    assert result == [{
        "id": "p1",
        "first_name": "Test",
        "position": "WR",
        "college_id": "alabama",
        "measurements": {"height_inches": 76, "weight_lbs": 210},
        "last_name": "Prospect",
        "athletic_scores": [{"source_name": "pff", "metric_name": "grade", "score": 90}],
    }]


def test_weekly_refresh_persists_merged_profile_and_snapshot() -> None:
    """The coordinator should persist one merged player and its source measurement."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    provider = StaticProvider([{"id": "p1", "first_name": "Test", "last_name": "Prospect", "position": "WR", "college_id": "alabama", "measurements": {"source_name": "weekly", "height_inches": 76}}])

    with Session(engine) as session:
        count = run_weekly_prospect_refresh(session, 2027, [provider], datetime(2026, 9, 16))
        assert count == 1
        assert session.query(PlayerRecord).count() == 1
        assert session.query(PlayerMeasurementRecord).count() == 1
