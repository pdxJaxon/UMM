"""Tests for leakage-aware historical draft backtesting."""

from datetime import date

import pytest

from app.services.historical_backtest import HistoricalDraftDataset, run_historical_backtest


def _dataset(year: int = 2024, as_of: date = date(2024, 3, 1)) -> HistoricalDraftDataset:
    return HistoricalDraftDataset(
        draft_year=year,
        as_of=as_of,
        team_needs={"team-1": ({"position_code": "QB", "need_score": 90},)},
        prospects=(
            {"player_id": "player-a", "position": "QB"},
            {"player_id": "player-b", "position": "WR"},
        ),
        team_staff={"team-1": ({"role_type": "gm", "person_id": "gm-a"},)},
        actual_picks={"team-1": ({"pick_number": 1, "player_id": "player-a"},)},
    )


def test_backtest_runs_predictor_with_historical_snapshot_and_aggregates_counts() -> None:
    """Backtests should report weighted aggregate rates across evaluated picks."""
    calls = []

    def predictor(year, team_id, dataset):
        calls.append((year, team_id, dataset.as_of))
        return [{"pick_number": 1, "player_id": "player-a"}]

    result = run_historical_backtest([_dataset()], predictor)

    assert calls == [(2024, "team-1", date(2024, 3, 1))]
    assert result.seasons == (2024,)
    assert result.aggregate["evaluated_picks"] == 1
    assert result.aggregate["exact_pick_rate"] == 100.0
    assert result.aggregate["player_hit_rate"] == 100.0


def test_backtest_rejects_post_draft_information() -> None:
    """A snapshot after April cannot be used to claim pre-draft accuracy."""
    with pytest.raises(ValueError, match="observed after"):
        run_historical_backtest([_dataset(as_of=date(2024, 5, 1))], lambda *_: [])


def test_backtest_rejects_actual_players_missing_from_snapshot() -> None:
    """Historical results must be explainable from the available prospect set."""
    dataset = _dataset()
    invalid = HistoricalDraftDataset(
        draft_year=dataset.draft_year,
        as_of=dataset.as_of,
        team_needs=dataset.team_needs,
        prospects=dataset.prospects,
        team_staff=dataset.team_staff,
        actual_picks={"team-1": ({"pick_number": 1, "player_id": "missing"},)},
    )

    with pytest.raises(ValueError, match="missing"):
        run_historical_backtest([invalid], lambda *_: [])