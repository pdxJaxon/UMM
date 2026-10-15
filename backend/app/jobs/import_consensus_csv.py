"""Preview or atomically import a local consensus prospect CSV."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.services.consensus_csv import read_consensus_csv
from app.services.prospect_board_import import import_board_snapshot


def main() -> int:
    """Require explicit snapshot metadata and opt-in database writes."""
    parser = argparse.ArgumentParser(description="Import a projected consensus prospect CSV; dry-run by default")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--draft-year", type=int, required=True)
    parser.add_argument("--snapshot-date", type=date.fromisoformat, required=True, help="Source date: YYYY-MM-DD")
    parser.add_argument("--limit", type=int, help="Map/import the top N after validating file structure and identities")
    parser.add_argument("--identity-map", type=Path, help="Reviewed JSON object: source key to existing player ID")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    snapshot = read_consensus_csv(
        args.csv, draft_year=args.draft_year, snapshot_date=args.snapshot_date, limit=args.limit,
    )
    overrides = None
    if args.identity_map:
        overrides = json.loads(args.identity_map.read_text(encoding="utf-8-sig"))
        if not isinstance(overrides, dict) or not all(
            isinstance(key, str) and isinstance(value, str) and value for key, value in overrides.items()
        ):
            parser.error("Identity map must be a JSON object mapping source keys to existing player IDs")
    with SessionLocal() as session:
        report = import_board_snapshot(session, snapshot, overrides, commit=args.commit)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
