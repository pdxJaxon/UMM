"""Tests for leakage-aware historical draft backtesting."""

from datetime import date
import json
from unittest.mock import Mock

import pytest

from app.services.historical_backtest import (
    build_deterministic_replay,
    deterministic_replay_predictor,
    FileHistoricalDraftDatasetProvider,
    FileDraftPicksProvider,
    FileProspectSource,
    HistoricalDraftDataset,
    NflverseHistoricalDatasetProvider,
    run_historical_backtest,
)
import app.jobs.run_historical_backtest as backtest_job
from app.jobs.run_historical_backtest import run_pilot


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


def test_backtest_accepts_late_pre_draft_snapshot() -> None:
    """Snapshots remain valid until the actual season draft begins."""
    dataset = _dataset(as_of=date(2024, 4, 10))

    result = run_historical_backtest([dataset], lambda *_: [{"pick_number": 1, "player_id": "player-a"}])

    assert result.aggregate["exact_pick_rate"] == 100.0


def test_backtest_rejects_snapshot_from_draft_start_date() -> None:
    with pytest.raises(ValueError, match="observed after"):
        run_historical_backtest([_dataset(as_of=date(2024, 4, 25))], lambda *_: [])


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


def test_backtest_can_report_unmatched_actuals_without_scoring_them() -> None:
    """Pilot mode should preserve strict validation while supporting partial source coverage."""
    dataset = _dataset()
    invalid = HistoricalDraftDataset(
        draft_year=dataset.draft_year,
        as_of=dataset.as_of,
        team_needs=dataset.team_needs,
        prospects=dataset.prospects,
        team_staff=dataset.team_staff,
        actual_picks={"team-1": (
            {"pick_number": 1, "player_id": "player-a"},
            {"pick_number": 2, "player_id": "missing"},
        )},
    )

    result = run_historical_backtest(
        [invalid],
        lambda *_: [{"pick_number": 1, "player_id": "player-a"}],
        allow_unmatched_actuals=True,
    )

    assert result.aggregate["unmatched_actuals"] == 1
    assert result.aggregate["evaluated_picks"] == 1


def test_backtest_aggregates_error_by_matched_player_count() -> None:
    """One team's lone match must not outweigh another team's three matches."""
    dataset = HistoricalDraftDataset(
        draft_year=2024,
        as_of=date(2024, 3, 1),
        team_needs={},
        prospects=tuple({"player_id": player_id} for player_id in ("a", "b", "c", "d", "e")),
        team_staff={},
        actual_picks={
            "team-1": ({"pick_number": 1, "player_id": "a"},),
            "team-2": (
                {"pick_number": 2, "player_id": "b"},
                {"pick_number": 3, "player_id": "c"},
                {"pick_number": 4, "player_id": "d"},
                {"pick_number": 5, "player_id": "e"},
            ),
        },
    )
    predictions = {
        "team-1": ({"pick_number": 13, "player_id": "a"},),
        "team-2": (
            {"pick_number": 2, "player_id": "b"},
            {"pick_number": 3, "player_id": "c"},
            {"pick_number": 4, "player_id": "d"},
        ),
    }

    result = run_historical_backtest([dataset], lambda _year, team_id, _dataset: predictions[team_id])

    assert result.aggregate["player_hits"] == 4
    assert result.aggregate["mean_absolute_pick_error"] == 3.0


def test_backtest_without_matched_players_has_no_aggregate_pick_error() -> None:
    """A missing prediction is not evidence of zero pick-number error."""
    result = run_historical_backtest([_dataset()], lambda *_: [])

    assert result.aggregate["player_hits"] == 0
    assert result.aggregate["mean_absolute_pick_error"] is None


def test_unmatched_early_outcome_does_not_consume_a_replay_candidate() -> None:
    """Unscored unknown outcomes must not change the predictions for later picks."""
    dataset = HistoricalDraftDataset(
        draft_year=2024,
        as_of=date(2024, 3, 1),
        team_needs={},
        prospects=({"player_id": "player-a"}, {"player_id": "player-b"}),
        team_staff={},
        actual_picks={
            "team-1": ({"pick_number": 1, "player_id": "missing"},),
            "team-2": ({"pick_number": 2, "player_id": "player-a"},),
        },
    )

    replay = build_deterministic_replay(dataset)

    assert replay["team-1"] == ()
    assert replay["team-2"] == ({"pick_number": 2, "player_id": "player-a"},)
    result = run_historical_backtest(
        [dataset], deterministic_replay_predictor(dataset), allow_unmatched_actuals=True,
    )
    assert result.aggregate["unmatched_actuals"] == 1
    assert result.aggregate["evaluated_picks"] == 1
    assert result.aggregate["exact_pick_rate"] == 100.0
    report = run_pilot([2024], type("Provider", (), {"load": lambda _self, _years: [dataset]})())
    assert report["aggregate"]["exact_pick_rate"] == 100.0


def test_file_provider_loads_and_filters_normalized_snapshots(tmp_path) -> None:
    """A normalized JSON file should feed the same immutable replay contract."""
    path = tmp_path / "historical-datasets.json"
    path.write_text(json.dumps({"datasets": [{
        "draft_year": 2024,
        "as_of": "2024-03-01",
        "team_needs": {"team-1": [{"position_code": "QB"}]},
        "prospects": [{"player_id": "player-a"}],
        "team_staff": {"team-1": [{"role_type": "gm", "person_id": "gm-a"}]},
        "actual_picks": {"team-1": [{"pick_number": 1, "player_id": "player-a"}]},
    }, {
        "draft_year": 2023,
        "as_of": "2023-03-01",
        "team_needs": {},
        "prospects": [],
        "team_staff": {},
        "actual_picks": {},
    }]}), encoding="utf-8")

    snapshots = FileHistoricalDraftDatasetProvider(path).load([2024])

    assert len(snapshots) == 1
    assert snapshots[0].draft_year == 2024
    assert snapshots[0].team_needs["team-1"][0]["position_code"] == "QB"
    assert isinstance(snapshots[0].actual_picks["team-1"], tuple)


def test_file_provider_loads_standalone_snapshot_object(tmp_path) -> None:
    path = tmp_path / "historical-dataset.json"
    path.write_text(json.dumps({
        "draft_year": 2024,
        "as_of": "2024-04-10",
        "prospects": [{"player_id": "player-a"}],
    }), encoding="utf-8")

    snapshots = FileHistoricalDraftDatasetProvider(path).load()

    assert len(snapshots) == 1
    assert snapshots[0].draft_year == 2024
    assert snapshots[0].as_of == date(2024, 4, 10)


def test_deterministic_replay_scores_needs_and_removes_selected_players() -> None:
    """Replay should use team needs and never select the same player twice."""
    dataset = HistoricalDraftDataset(
        draft_year=2024,
        as_of=date(2024, 3, 1),
        team_needs={"team-1": ({"position_code": "QB", "need_score": 100},), "team-2": ()},
        prospects=(
            {"player_id": "wr", "position": "WR", "ranking_values": {"overall": 100}},
            {"player_id": "qb", "position": "QB", "ranking_values": {"overall": 90}},
        ),
        team_staff={},
        actual_picks={
            "team-1": ({"pick_number": 1, "player_id": "qb"},),
            "team-2": ({"pick_number": 2, "player_id": "wr"},),
        },
    )

    replay = build_deterministic_replay(dataset)

    assert replay["team-1"] == ({"pick_number": 1, "player_id": "qb"},)
    assert replay["team-2"] == ({"pick_number": 2, "player_id": "wr"},)
    assert deterministic_replay_predictor(dataset)(2024, "team-1", dataset) == replay["team-1"]


def test_nflverse_provider_builds_snapshot_from_prospects_and_actual_picks() -> None:
    """The first real-data adapter should preserve source IDs and season boundaries."""
    provider = Mock()
    provider.load_combine.return_value = [{
        "pfr_id": "prospect-a",
        "player_name": "Example Prospect",
        "pos": "QB",
        "school": "Example University",
    }]
    provider.load_players.return_value = []
    provider.load_draft_picks.return_value = [{
        "season": 2024,
        "round": 1,
        "pick": 1,
        "team": "team-1",
        "pfr_player_id": "prospect-a",
    }]

    snapshots = NflverseHistoricalDatasetProvider(provider).load([2024])

    assert len(snapshots) == 1
    assert snapshots[0].as_of == date(2024, 3, 1)
    assert snapshots[0].prospects[0]["id"] == "prospect-a"
    assert snapshots[0].actual_picks == {"team-1": ({"pick_number": 1, "player_id": "prospect-a"},)}


def test_pilot_returns_accuracy_and_input_coverage() -> None:
    """The pilot report must expose both results and which historical signals exist."""
    dataset = _dataset()
    report = run_pilot([2024], type("Provider", (), {"load": lambda _self, _years: [dataset]})())

    assert report["seasons"] == [2024]
    assert report["aggregate"]["exact_pick_rate"] == 100.0
    assert report["coverage"] == [{
        "draft_year": 2024,
        "as_of": "2024-03-01",
        "prospects": 2,
        "teams_with_actual_picks": 1,
        "actual_picks": 1,
        "prospects_missing_from_outcomes": 0,
        "teams_with_needs": 1,
        "teams_with_staff": 1,
        "teams_with_tendencies": 0,
    }]


def test_pilot_builds_one_replay_per_dataset(monkeypatch) -> None:
    dataset = HistoricalDraftDataset(
        draft_year=2024,
        as_of=date(2024, 3, 1),
        team_needs={},
        prospects=({"player_id": "player-a"},),
        team_staff={},
        actual_picks={
            "team-1": ({"pick_number": 1, "player_id": "player-a"},),
            "team-2": ({"pick_number": 2, "player_id": "player-a"},),
        },
    )
    original_replay = backtest_job.build_deterministic_replay
    calls = []

    def counted_replay(snapshot):
        calls.append(snapshot)
        return original_replay(snapshot)

    monkeypatch.setattr(backtest_job, "build_deterministic_replay", counted_replay)

    run_pilot([2024], type("Provider", (), {"load": lambda _self, _years: [dataset]})())

    assert calls == [dataset]


def test_file_draft_picks_provider_reads_parquet_seasons(tmp_path) -> None:
    """Local parquet outcomes should be available without downloading draft data."""
    polars = pytest.importorskip("polars")
    path = tmp_path / "draft_picks.parquet"
    polars.DataFrame([
        {"season": 2024, "pick": 1, "team": "team-1", "gsis_id": "player-a"},
        {"season": 2023, "pick": 1, "team": "team-2", "gsis_id": "player-b"},
    ]).write_parquet(path)

    rows = FileDraftPicksProvider(path).load_draft_picks([2024])

    assert rows == [{"season": 2024, "pick": 1, "team": "team-1", "gsis_id": "player-a"}]


def test_file_prospect_source_reads_combine_and_players(tmp_path) -> None:
    """Local prospect parquet files should replace both network downloads."""
    polars = pytest.importorskip("polars")
    combine_path = tmp_path / "combine.parquet"
    players_path = tmp_path / "players.parquet"
    polars.DataFrame([{"season": 2024, "pfr_id": "player-a", "player_name": "Example", "pos": "QB"}]).write_parquet(combine_path)
    polars.DataFrame([{"pfr_id": "player-a", "display_name": "Example", "position": "QB"}]).write_parquet(players_path)

    source = FileProspectSource(combine_path, players_path)

    assert source.load_combine([2024])[0]["pfr_id"] == "player-a"
    assert source.load_players()[0]["pfr_id"] == "player-a"