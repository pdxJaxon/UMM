"""Leakage-aware historical mock-draft backtesting."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

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


@dataclass(frozen=True)
class BacktestResult:
    """Per-season and aggregate accuracy results from a backtest run."""

    seasons: tuple[int, ...]
    team_results: tuple[dict[str, object], ...]
    aggregate: dict[str, object]


Predictor = Callable[[int, str, HistoricalDraftDataset], Iterable[Mapping[str, object]]]


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