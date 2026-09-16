"""Tests for versioned prospect profile and measurement ingestion."""

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import PlayerAthleticScoreRecord, PlayerMeasurementRecord, PlayerRecord
from app.db.session import Base
from app.services.prospect_ingestion import ProspectIngestionService


class FakeProspectProvider:
    """Deterministic provider fixture representing a weekly source pull."""

    def __init__(self, payload: list[dict[str, object]]) -> None:
        """Store the payload returned by the simulated provider."""
        self.payload = payload

    def fetch(self, draft_year: int) -> list[dict[str, object]]:
        """Return the configured detailed prospect payload."""
        return self.payload


def test_refresh_persists_profile_measurements_and_scores() -> None:
    """A refresh should preserve detailed measurements and athletic scores."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    payload = {
        "id": "prospect-1",
        "first_name": "Test",
        "last_name": "Prospect",
        "position": "QB",
        "college_id": "alabama",
        "measurements": {
            "source_name": "combine-feed",
            "source_record_id": "cp-1",
            "age_years": 21.4,
            "height_inches": 76,
            "weight_lbs": 215,
            "hand_inches": 9.5,
            "arm_inches": 32.0,
        },
        "athletic_scores": [
            {"source_name": "ras", "metric_name": "overall", "score": 9.2, "score_scale": "0-10"},
            {"source_name": "sparq", "metric_name": "total", "score": 88.5, "score_scale": "source-scale"},
        ],
    }

    with Session(engine) as session:
        service = ProspectIngestionService(session, FakeProspectProvider([payload]))
        processed = service.refresh(2027, datetime(2026, 9, 16))

        assert processed == 1
        assert session.query(PlayerRecord).count() == 1
        assert session.query(PlayerMeasurementRecord).count() == 1
        assert session.query(PlayerAthleticScoreRecord).count() == 2


def test_refresh_updates_profile_but_appends_new_measurement_snapshot() -> None:
    """A later weekly source result should update profile fields and retain history."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    first = {"id": "prospect-1", "first_name": "Test", "last_name": "Prospect", "position": "QB", "college_id": "alabama"}
    second = {"id": "prospect-1", "first_name": "Updated", "last_name": "Prospect", "position": "QB", "college_id": "alabama", "measurements": {"source_name": "pro-day", "height_inches": 76.5}}

    with Session(engine) as session:
        ProspectIngestionService(session, FakeProspectProvider([first])).refresh(2027, datetime(2026, 9, 1))
        ProspectIngestionService(session, FakeProspectProvider([second])).refresh(2027, datetime(2027, 3, 1))

        assert session.get(PlayerRecord, "prospect-1").first_name == "Updated"
        assert session.query(PlayerMeasurementRecord).count() == 1
