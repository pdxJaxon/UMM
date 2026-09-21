"""CLI entry point for historical draft-trade tendency refreshes."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.db.initialize import initialize_schema, seed_reference_data
from app.db.session import SessionLocal
from app.services.nflverse_provider import NflverseProvider
from app.services.trade_history import (
    DraftTradeHistoryIngestionService,
    FileDraftTradeHistoryProvider,
    LeadershipIngestionService,
    NflverseDraftTradeHistoryProvider,
    _read_records,
)


def main() -> int:
    """Refresh inferred draft trades for a range of historical seasons."""
    parser = argparse.ArgumentParser(description="Refresh UMockMe historical draft trades")
    parser.add_argument("--start-season", type=int, required=True)
    parser.add_argument("--end-season", type=int, required=True)
    parser.add_argument("--trade-history-file", type=str)
    parser.add_argument("--leadership-file", type=str)
    args = parser.parse_args()
    if args.end_season < args.start_season:
        parser.error("--end-season must be greater than or equal to --start-season")

    initialize_schema()
    session = SessionLocal()
    try:
        seed_reference_data(session)
        seasons = list(range(args.start_season, args.end_season + 1))
        provider = (
            FileDraftTradeHistoryProvider(args.trade_history_file)
            if args.trade_history_file
            else NflverseDraftTradeHistoryProvider(NflverseProvider())
        )
        processed = DraftTradeHistoryIngestionService(session, provider).refresh(seasons)
        leadership_processed = 0
        if args.leadership_file:
            leadership_processed = LeadershipIngestionService(session).refresh(_read_records(Path(args.leadership_file)))
        print(f"Historical trade refresh succeeded: {processed} events, {leadership_processed} leadership records processed")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())