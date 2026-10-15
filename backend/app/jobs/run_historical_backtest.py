"""CLI entry point for deterministic historical draft backtests."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from typing import Any

from app.services.historical_backtest import (
    FileDraftPicksProvider,
    FileProspectSource,
    HistoricalDraftDataset,
    NflverseHistoricalDatasetProvider,
    run_historical_backtest,
)


def run_pilot(
    seasons: Iterable[int],
    dataset_provider: Any | None = None,
    draft_picks_file: str | None = None,
    combine_file: str | None = None,
    players_file: str | None = None,
) -> dict[str, object]:
    """Load seasons, run deterministic replay, and return metrics plus coverage."""
    years = [int(season) for season in seasons]
    if dataset_provider is not None:
        provider = dataset_provider
    else:
        if bool(combine_file) != bool(players_file):
            raise ValueError("--combine-file and --players-file must be provided together")
        provider = NflverseHistoricalDatasetProvider(
            draft_picks_source=FileDraftPicksProvider(draft_picks_file) if draft_picks_file else None,
            prospect_source=FileProspectSource(combine_file, players_file) if combine_file else None,
        )
    datasets: list[HistoricalDraftDataset] = provider.load(years)

    def predictor(year: int, team_id: str, dataset: HistoricalDraftDataset):
        from app.services.historical_backtest import build_deterministic_replay

        return build_deterministic_replay(dataset).get(team_id, ())

    result = run_historical_backtest(datasets, predictor, allow_unmatched_actuals=True)
    return {
        "seasons": list(result.seasons),
        "aggregate": result.aggregate,
        "team_results": list(result.team_results),
        "coverage": [_coverage(dataset) for dataset in datasets],
    }


def main() -> int:
    """Run the pilot and print a JSON report suitable for CI or later tuning."""
    parser = argparse.ArgumentParser(description="Run a deterministic UMockMe historical draft backtest")
    parser.add_argument("--start-season", type=int, required=True)
    parser.add_argument("--end-season", type=int, required=True)
    parser.add_argument("--draft-picks-file", type=str, help="Local parquet draft-pick outcomes file")
    parser.add_argument("--combine-file", type=str, help="Local parquet combine measurements file")
    parser.add_argument("--players-file", type=str, help="Local parquet player identity file")
    args = parser.parse_args()
    if args.end_season < args.start_season:
        parser.error("--end-season must be greater than or equal to --start-season")

    report = run_pilot(
        range(args.start_season, args.end_season + 1),
        draft_picks_file=args.draft_picks_file,
        combine_file=args.combine_file,
        players_file=args.players_file,
    )
    print(json.dumps(report, sort_keys=True))
    return 0


def _coverage(dataset: HistoricalDraftDataset) -> dict[str, object]:
    """Report populated historical inputs without implying missing data is valid."""
    return {
        "draft_year": dataset.draft_year,
        "as_of": dataset.as_of.isoformat(),
        "prospects": len(dataset.prospects),
        "teams_with_actual_picks": len(dataset.actual_picks),
        "actual_picks": sum(len(picks) for picks in dataset.actual_picks.values()),
        "prospects_missing_from_outcomes": sum(
            1
            for picks in dataset.actual_picks.values()
            for pick in picks
            if str(pick["player_id"]) not in {str(prospect.get("player_id") or prospect.get("id")) for prospect in dataset.prospects}
        ),
        "teams_with_needs": len(dataset.team_needs),
        "teams_with_staff": len(dataset.team_staff),
        "teams_with_tendencies": len(dataset.team_tendencies),
    }


if __name__ == "__main__":
    raise SystemExit(main())