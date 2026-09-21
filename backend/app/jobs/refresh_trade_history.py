"""CLI entry point for historical draft-trade tendency refreshes."""

from __future__ import annotations

import argparse

from app.db.initialize import initialize_schema, seed_reference_data
from app.db.session import SessionLocal
from app.services.nflverse_provider import NflverseProvider
from app.services.trade_history import DraftTradeHistoryIngestionService, NflverseDraftTradeHistoryProvider


def main() -> int:
    """Refresh inferred draft trades for a range of historical seasons."""
    parser = argparse.ArgumentParser(description="Refresh UMockMe historical draft trades")
    parser.add_argument("--start-season", type=int, required=True)
    parser.add_argument("--end-season", type=int, required=True)
    args = parser.parse_args()
    if args.end_season < args.start_season:
        parser.error("--end-season must be greater than or equal to --start-season")

    initialize_schema()
    session = SessionLocal()
    try:
        seed_reference_data(session)
        processed = DraftTradeHistoryIngestionService(
            session,
            NflverseDraftTradeHistoryProvider(NflverseProvider()),
        ).refresh(list(range(args.start_season, args.end_season + 1)))
        print(f"Historical trade refresh succeeded: {processed} events processed")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())