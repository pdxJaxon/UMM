"""CLI entry point for the weekly prospect refresh."""

from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.db.initialize import initialize_schema, seed_reference_data
from app.services.nflverse_prospect_provider import NflverseProspectProvider
from app.services.refresh_runner import run_refresh_with_retries


def main() -> int:
    """Run the prospect refresh job and return a process exit code."""
    parser = argparse.ArgumentParser(description="Refresh UMockMe draft prospects")
    parser.add_argument("--draft-year", type=int, required=True)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=5.0)
    args = parser.parse_args()

    initialize_schema()
    session = SessionLocal()
    try:
        seed_reference_data(session)
        processed = run_refresh_with_retries(
            session,
            args.draft_year,
            [NflverseProspectProvider()],
            args.max_attempts,
            args.retry_delay_seconds,
        )
        print(f"Prospect refresh succeeded: {processed} records processed")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())