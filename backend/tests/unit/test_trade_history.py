"""Tests for historical draft-trade extraction and tendency refreshes."""

from datetime import UTC, datetime
import json
import sys
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.initialize import TEAMS
from app.db.models import HistoricalDraftTradeRecord, TeamDraftingTendencyRecord, TeamLeadershipRecord, TeamRecord
from app.db.session import Base
from app.jobs import refresh_trade_history
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


def test_refresh_removes_obsolete_actor_tendencies_without_touching_other_sources() -> None:
    """Recomputed counts must remove stale actor rows from previous trade analysis."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(TeamRecord(**team) for team in TEAMS[:3])
        session.add(HistoricalDraftTradeRecord(
            draft_year=2024,
            pick_number=1,
            moving_up_team_id="team-2",
            moving_down_team_id="team-1",
            general_manager_id="gm-a",
            head_coach_id="coach-a",
            source_name="nflverse-draft-picks",
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ))
        session.add_all([
            TeamDraftingTendencyRecord(
                team_id="team-1", draft_year=None, actor_type="gm", actor_id="gm-a",
                tendency_type="trade_down", preference_score=100, confidence_score=20,
                sample_size=1, source_name="historical-trade-analysis",
                observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            TeamDraftingTendencyRecord(
                team_id="team-1", draft_year=None, actor_type="gm", actor_id="gm-a",
                tendency_type="trade_down", preference_score=100, confidence_score=20,
                sample_size=1, source_name="manual",
                observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ])
        session.commit()
        provider = Mock()
        provider.load_draft_picks.return_value = []
        service = DraftTradeHistoryIngestionService(session, NflverseDraftTradeHistoryProvider(provider))

        assert service.refresh([2024]) == 0

        assert session.query(TeamDraftingTendencyRecord).filter_by(
            source_name="historical-trade-analysis", team_id="team-1", actor_id="gm-a"
        ).count() == 0
        assert session.query(TeamDraftingTendencyRecord).filter_by(
            source_name="historical-trade-analysis", team_id="team-2",
            actor_type="gm", actor_id="gm-a", tendency_type="trade_up", sample_size=1,
        ).count() == 1
        assert session.query(TeamDraftingTendencyRecord).filter_by(source_name="manual").count() == 1


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


@pytest.mark.parametrize("original_team,selecting_team", [
    ("ARI", "ari"),
    ("team-1", "ARI"),
    ("ARI", "TEAM-1"),
])
def test_refresh_ignores_equivalent_team_ownership(original_team, selecting_team) -> None:
    """Different aliases of one team must not create self-trades or tendencies."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(TeamRecord(**team) for team in TEAMS[:3])
        session.commit()
        provider = Mock()
        provider.load_draft_picks.return_value = [
            {"season": 2024, "pick": 1, "original_team": original_team, "team": selecting_team},
        ]
        service = DraftTradeHistoryIngestionService(session, NflverseDraftTradeHistoryProvider(provider))

        assert service.refresh([2024]) == 0
        assert session.query(HistoricalDraftTradeRecord).count() == 0
        assert session.query(TeamDraftingTendencyRecord).count() == 0


def test_refresh_resolves_canonical_ids_for_real_trades() -> None:
    """Case normalization must preserve legitimate trades between different teams."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(TeamRecord(**team) for team in TEAMS[:3])
        session.commit()
        provider = Mock()
        provider.load_draft_picks.return_value = [
            {"season": 2024, "pick": 1, "original_team_id": " TEAM-1 ", "team_id": "team-2"},
        ]
        service = DraftTradeHistoryIngestionService(session, NflverseDraftTradeHistoryProvider(provider))

        assert service.refresh([2024]) == 1
        event = session.query(HistoricalDraftTradeRecord).one()
        assert event.moving_up_team_id == "team-2"
        assert event.moving_down_team_id == "team-1"


@pytest.mark.parametrize("team_token", ["team-2", "TEAM-2", "atl", " ATL "])
def test_leadership_refresh_resolves_normalized_team_ids(team_token) -> None:
    """Leadership files accept canonical IDs as well as team abbreviations."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(TeamRecord(**team) for team in TEAMS[:3])
        session.commit()

        assert LeadershipIngestionService(session).refresh([{
            "team_id": team_token,
            "role": "gm",
            "person_id": "gm-a",
            "start_year": 2024,
        }]) == 1
        assert session.query(TeamLeadershipRecord).one().team_id == "team-2"


@pytest.mark.parametrize("file_format", ["json", "csv"])
def test_refresh_cli_imports_file_history_and_leadership(tmp_path, monkeypatch, capsys, file_format) -> None:
    """The documented CLI must normalize file rows before persisting history."""
    history_file = tmp_path / f"trades.{file_format}"
    history_file.write_text(json.dumps([
        {"season": 2024, "pick": 1, "original_team": "ARI", "team": "ATL"},
        {"season": 2023, "pick": 2, "original_team": "ARI", "team": "ATL"},
    ]) if file_format == "json" else (
        "season,pick,original_team,team\n2024,1,ARI,ATL\n2023,2,ARI,ATL\n"
    ), encoding="utf-8")
    leadership_file = tmp_path / "leadership.json"
    leadership_file.write_text(json.dumps([{
        "team_id": "team-2", "role": "gm", "person_id": "gm-a", "start_year": 2024,
    }]), encoding="utf-8")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(refresh_trade_history, "initialize_schema", lambda: None)
    monkeypatch.setattr(refresh_trade_history, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(sys, "argv", [
        "refresh_trade_history", "--start-season", "2024", "--end-season", "2024",
        "--trade-history-file", str(history_file), "--leadership-file", str(leadership_file),
    ])

    assert refresh_trade_history.main() == 0
    assert "1 events, 1 leadership records processed" in capsys.readouterr().out
    with Session(engine) as session:
        event = session.query(HistoricalDraftTradeRecord).one()
        assert event.moving_up_team_id == "team-2"
        assert event.moving_down_team_id == "team-1"
        assert event.source_name == f"file:trades.{file_format}"
        assert session.query(TeamLeadershipRecord).one().team_id == "team-2"