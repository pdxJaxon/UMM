"""Leakage-aware historical mock-draft backtesting."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
import json
from pathlib import Path
from typing import Any

from app.services.draft_scoring import DraftScoreWeights, calculate_draft_score
from app.services.nflverse_prospect_provider import NflverseProspectProvider
from app.services.nflverse_provider import NflverseProvider
from app.services.prediction_accuracy import evaluate_prediction_accuracy


@dataclass(frozen=True)
class HistoricalDraftDataset:
    """All information available to the engine for one historical draft."""

    draft_year: int
    as_of: date
    team_needs: Mapping[str, tuple[Mapping[str, object], ...]]
    prospects: tuple[Mapping[str, object], ...]
    team_staff: Mapping[str, tuple[Mapping[str, object], ...]]
    actual_picks: Mapping[str, tuple[Mapping[str, object], ...]]
    team_tendencies: Mapping[str, tuple[Mapping[str, object], ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestResult:
    """Per-season and aggregate accuracy results from a backtest run."""

    seasons: tuple[int, ...]
    team_results: tuple[dict[str, object], ...]
    aggregate: dict[str, object]


Predictor = Callable[[int, str, HistoricalDraftDataset], Iterable[Mapping[str, object]]]


def build_deterministic_replay(
    dataset: HistoricalDraftDataset,
    weights: DraftScoreWeights | None = None,
) -> dict[str, tuple[dict[str, object], ...]]:
    """Replay historical pick order using only the supplied pre-draft snapshot."""
    candidates = [dict(prospect) for prospect in dataset.prospects]
    selected: set[str] = set()
    predictions: dict[str, list[dict[str, object]]] = {team_id: [] for team_id in dataset.actual_picks}
    events = sorted(
        ((int(pick["pick_number"]), team_id, pick) for team_id, picks in dataset.actual_picks.items() for pick in picks),
        key=lambda event: event[0],
    )
    for pick_number, team_id, _actual_pick in events:
        ranked = _rank_available_candidates(dataset, team_id, pick_number, candidates, selected, weights)
        if not ranked:
            continue
        selected_player_id = str(ranked[0]["player_id"])
        predictions[team_id].append({"pick_number": pick_number, "player_id": selected_player_id})
        selected.add(selected_player_id)
    return {team_id: tuple(team_predictions) for team_id, team_predictions in predictions.items()}


def deterministic_replay_predictor(
    dataset: HistoricalDraftDataset,
    weights: DraftScoreWeights | None = None,
) -> Predictor:
    """Create a backtest predictor backed by one deterministic historical replay."""
    replay = build_deterministic_replay(dataset, weights)
    return lambda _draft_year, team_id, _dataset: replay.get(team_id, ())


class FileHistoricalDraftDatasetProvider:
    """Load normalized historical snapshots from a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self, seasons: Iterable[int] | None = None) -> list[HistoricalDraftDataset]:
        """Return snapshots limited to the requested seasons, when provided."""
        with self.path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        records = payload.get("datasets") if isinstance(payload, dict) else payload
        if isinstance(records, dict):
            records = [records]
        if not isinstance(records, list):
            raise ValueError("Historical dataset file must contain a snapshot or a datasets array")
        requested = {int(season) for season in seasons} if seasons is not None else None
        snapshots = [_snapshot_from_record(record) for record in records]
        return [snapshot for snapshot in snapshots if requested is None or snapshot.draft_year in requested]


class NflverseHistoricalDatasetProvider:
    """Build normalized snapshots from nflverse combine and draft-pick data."""

    def __init__(self, provider: NflverseProvider | None = None, draft_picks_source: Any | None = None) -> None:
        self.provider = provider or NflverseProvider()
        self.draft_picks_source = draft_picks_source or self.provider

    def load(self, seasons: Iterable[int]) -> list[HistoricalDraftDataset]:
        """Load pre-draft prospects and actual outcomes for each requested season."""
        years = [int(season) for season in seasons]
        prospect_provider = NflverseProspectProvider(self.provider)
        picks_by_year: dict[int, list[dict[str, Any]]] = {year: [] for year in years}
        for row in _rows(self.draft_picks_source.load_draft_picks(years)):
            year = _integer(row, "draft_year", "season", "year")
            if year in picks_by_year:
                picks_by_year[year].append(row)
        datasets = []
        for year in years:
            actual_picks: dict[str, list[dict[str, object]]] = {}
            for row in picks_by_year[year]:
                team_id = _first_value(row, "team_id", "team", "team_abbr", "posteam")
                player_id = _first_value(row, "player_id", "gsis_id", "pfr_id", "pfr_player_id")
                pick_number = _integer(row, "pick_number", "pick", "overall_pick")
                if team_id and player_id and pick_number:
                    actual_picks.setdefault(team_id, []).append({"pick_number": pick_number, "player_id": player_id})
            datasets.append(HistoricalDraftDataset(
                draft_year=year,
                as_of=date(year, 3, 1),
                team_needs={},
                prospects=tuple(prospect_provider.fetch(year)),
                team_staff={},
                actual_picks={team_id: tuple(picks) for team_id, picks in actual_picks.items()},
            ))
        return datasets


class FileDraftPicksProvider:
    """Load draft-pick outcomes from a local parquet file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load_draft_picks(self, seasons: Iterable[int]) -> list[dict[str, Any]]:
        """Return parquet rows limited to the requested seasons."""
        try:
            import polars as pl
        except ImportError as error:
            raise RuntimeError("Install polars to load parquet draft-pick data") from error
        frame = pl.read_parquet(self.path)
        requested = {int(season) for season in seasons}
        return [row for row in frame.to_dicts() if _integer(row, "draft_year", "season", "year") in requested]


def run_historical_backtest(
    datasets: Iterable[HistoricalDraftDataset],
    predictor: Predictor,
    *,
    evaluation_scope: str = "first_round",
) -> BacktestResult:
    """Run a predictor against historical picks without allowing future data.

    The predictor receives only one season dataset at a time. Dataset validation
    rejects snapshots whose ``as_of`` date is after that draft's first pick and
    rejects actual picks that reference prospects absent from the snapshot.
    """
    team_results: list[dict[str, object]] = []
    for dataset in sorted(datasets, key=lambda item: item.draft_year):
        if dataset.as_of > date(dataset.draft_year, 4, 1):
            raise ValueError(f"Dataset for {dataset.draft_year} contains information observed after the draft began")
        prospect_ids = {str(prospect.get("player_id") or prospect.get("id")) for prospect in dataset.prospects}
        for team_id, actual_picks in dataset.actual_picks.items():
            if any(str(pick["player_id"]) not in prospect_ids for pick in actual_picks):
                raise ValueError(f"Actual pick for {team_id} references a prospect missing from {dataset.draft_year} snapshot")
            predictions = list(predictor(dataset.draft_year, team_id, dataset))
            metrics = evaluate_prediction_accuracy(predictions, actual_picks)
            team_results.append({
                "draft_year": dataset.draft_year,
                "team_id": team_id,
                "evaluation_scope": evaluation_scope,
                **metrics,
            })

    return BacktestResult(
        seasons=tuple(sorted({int(result["draft_year"]) for result in team_results})),
        team_results=tuple(team_results),
        aggregate=_aggregate(team_results),
    )


def _aggregate(results: list[dict[str, object]]) -> dict[str, object]:
    """Aggregate counts and error across teams without averaging percentages."""
    evaluated_picks = sum(int(result["evaluated_picks"]) for result in results)
    exact_hits = sum(int(result["exact_hits"]) for result in results)
    player_hits = sum(int(result["player_hits"]) for result in results)
    errors = [
        float(result["mean_absolute_pick_error"])
        for result in results
        if result["mean_absolute_pick_error"] is not None
    ]
    return {
        "evaluated_teams": len(results),
        "evaluated_picks": evaluated_picks,
        "exact_hits": exact_hits,
        "player_hits": player_hits,
        "exact_pick_rate": round(exact_hits / evaluated_picks * 100, 2) if evaluated_picks else 0.0,
        "player_hit_rate": round(player_hits / evaluated_picks * 100, 2) if evaluated_picks else 0.0,
        "mean_absolute_pick_error": round(sum(errors) / len(errors), 2) if errors else None,
    }


def _snapshot_from_record(record: Any) -> HistoricalDraftDataset:
    """Normalize one file record without changing the source payload values."""
    if not isinstance(record, Mapping):
        raise ValueError("Each historical dataset must be an object")
    try:
        draft_year = int(record["draft_year"])
        as_of = date.fromisoformat(str(record["as_of"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Historical dataset requires draft_year and ISO as_of") from error
    return HistoricalDraftDataset(
        draft_year=draft_year,
        as_of=as_of,
        team_needs=_team_records(record.get("team_needs", {})),
        prospects=tuple(_records(record.get("prospects", []))),
        team_staff=_team_records(record.get("team_staff", {})),
        actual_picks=_team_records(record.get("actual_picks", {})),
        team_tendencies=_team_records(record.get("team_tendencies", {})),
    )


def _team_records(value: Any) -> dict[str, tuple[Mapping[str, object], ...]]:
    """Convert a team-keyed JSON object into immutable record tuples."""
    if not isinstance(value, Mapping):
        raise ValueError("Team-scoped historical data must be an object")
    return {str(team_id): tuple(_records(records)) for team_id, records in value.items()}


def _records(value: Any) -> list[Mapping[str, object]]:
    """Validate a JSON record collection while retaining each mapping."""
    if not isinstance(value, list) or any(not isinstance(record, Mapping) for record in value):
        raise ValueError("Historical data collections must contain object records")
    return list(value)


def _rows(value: Any) -> list[dict[str, Any]]:
    """Convert Polars, pandas, or list-like provider output to dictionaries."""
    if hasattr(value, "iter_rows"):
        return list(value.iter_rows(named=True))
    if hasattr(value, "to_dict"):
        try:
            return list(value.to_dict(orient="records"))
        except TypeError:
            pass
    return list(value)


def _integer(row: Mapping[str, Any], *names: str) -> int | None:
    """Return the first valid integer field from a provider row."""
    for name in names:
        if row.get(name) not in (None, ""):
            try:
                return int(row[name])
            except (TypeError, ValueError):
                return None
    return None


def _first_value(row: Mapping[str, Any], *names: str) -> str | None:
    """Return the first non-empty provider value as a stable string."""
    for name in names:
        if row.get(name) not in (None, ""):
            return str(row[name]).strip()
    return None


def _rank_available_candidates(
    dataset: HistoricalDraftDataset,
    team_id: str,
    pick_number: int,
    candidates: list[dict[str, object]],
    selected: set[str],
    weights: DraftScoreWeights | None,
) -> list[dict[str, object]]:
    """Score and rank available snapshot candidates for one historical pick."""
    ranked: list[tuple[dict[str, object], float]] = []
    for candidate in candidates:
        player_id = str(candidate.get("player_id") or candidate.get("id") or "")
        if not player_id or player_id in selected:
            continue
        candidate["id"] = player_id
        breakdown = calculate_draft_score(
            player=candidate,
            team_id=team_id,
            pick_number=pick_number,
            team_needs=dataset.team_needs.get(team_id, ()),
            tendencies=dataset.team_tendencies.get(team_id, ()),
            meetings=candidate.get("meetings", ()),
            external_picks=candidate.get("external_picks", ()),
            concerns=candidate.get("concerns", ()),
            ranking_values=candidate.get("ranking_values", {}),
            weights=weights,
        )
        ranked.append(({"player_id": player_id, "score": breakdown.final_score}, breakdown.final_score))
    ranked.sort(key=lambda item: (-item[1], item[0]["player_id"]))
    return [candidate for candidate, _score in ranked]