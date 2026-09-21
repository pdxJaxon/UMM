"""Tests for historical draft-trade extraction and tendency refreshes."""

from datetime import UTC, datetime
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.initialize import TEAMS
from app.db.models import HistoricalDraftTradeRecord, TeamDraftingTendencyRecord, TeamLeadershipRecord, TeamRecord
from app.db.session import Base
from app.services.trade_history import DraftTradeHistoryIngestionService, FileDraftTradeHistoryProvider, LeadershipIngestionService, NflverseDraftTradeHistoryProvider


def test_nflverse_trade_rows_require_explicit_original_owner() -> None:
    """The adapter must not infer trades from final selecting-team data alone."""
    provider = Mock()
    provider.load_draft_picks.return_value = [
        {"season": 2024, "pick": 1, "team": "ATL"},
        {"season": 2024, "pick": 2, "original_team": "ARI", "team": "ATL"},
    ]

    trades = NflverseDraftTradeHistoryProvider(provider).fetch([2024])

    assert trades == [{
        "draft_year": 2024,
        "pick_number": 2,
        "moving_up_team": "ATL",
        "moving_down_team": "ARI",
        "source_name": "nflverse-draft-picks",
        "raw_payload": {"season": 2024, "pick": 2, "original_team": "ARI", "team": "ATL"},
    }]


def test_refresh_persists_events_and_aggregate_direction_tendencies() -> None:
    """Historical events should be idempotent and produce confidence-aware scores."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all(TeamRecord(**team) for team in TEAMS[:3])
    session.commit()

    provider = Mock()
    provider.load_draft_picks.return_value = [
        {"season": 2024, "pick": 1, "original_team": "ARI", "team": "ATL"},
        {"season": 2025, "pick": 1, "original_team": "ARI", "team": "ATL"},
        {"season": 2025, "pick": 2, "original_team": "ATL", "team": "ARI"},
    ]
    service = DraftTradeHistoryIngestionService(session, NflverseDraftTradeHistoryProvider(provider))

    assert service.refresh([2024, 2025], datetime(2026, 1, 1, tzinfo=UTC)) == 3
    assert service.refresh([2024, 2025], datetime(2026, 1, 2, tzinfo=UTC)) == 0

    events = session.query(HistoricalDraftTradeRecord).all()
    atlanta_up = session.query(TeamDraftingTendencyRecord).filter_by(team_id="team-2", tendency_type="trade_up").one()
    arizona_down = session.query(TeamDraftingTendencyRecord).filter_by(team_id="team-1", tendency_type="trade_down").one()
    assert len(events) == 3
    assert atlanta_up.sample_size == 2
    assert atlanta_up.confidence_score == 60
    assert arizona_down.sample_size == 2
    assert float(arizona_down.preference_score) == 83.33


def test_file_provider_reads_json_and_filters_seasons(tmp_path) -> None:
    """Normalized JSON exports should be usable without changing the engine."""
    history_file = tmp_path / "trades.json"
    history_file.write_text(
        '[{"season": 2024, "pick": 1, "original_team": "ARI", "team": "ATL"}, '
        '{"season": 2023, "pick": 2, "original_team": "ARI", "team": "ATL"}]',
        encoding="utf-8",
    )

    rows = FileDraftTradeHistoryProvider(history_file).load_draft_picks([2024])

    assert rows == [{"season": 2024, "pick": 1, "original_team": "ARI", "team": "ATL"}]


def test_leadership_refresh_maps_team_abbreviations_and_is_idempotent() -> None:
    """Leadership imports should resolve team abbreviations and avoid duplicates."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all(TeamRecord(**team) for team in TEAMS[:3])
    session.commit()
    service = LeadershipIngestionService(session)
    records = [{
        "team": "ATL",
        "role": "General Manager",
        "person_id": "gm-a",
        "person_name": "GM A",
        "start_year": 2025,
    }]

    assert service.refresh(records) == 1
    assert service.refresh(records) == 0
    leadership = session.query(TeamLeadershipRecord).one()
    assert leadership.team_id == "team-2"
    assert leadership.role_type == "gm"