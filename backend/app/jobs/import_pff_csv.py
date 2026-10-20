"""Preview or import the newest authorized PFF CSV; suitable for nightly use."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.services.pff_csv import import_pff_csv, newest_pff_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Import PFF candidates; dry-run unless --commit is supplied")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--csv", type=Path)
    inputs.add_argument("--directory", type=Path, help="Inbox for one draft year, using dated PFF export names")
    parser.add_argument("--draft-year", type=int, required=True)
    parser.add_argument("--snapshot-date", type=date.fromisoformat, help="Required with --csv; YYYY-MM-DD")
    parser.add_argument("--min-prospects", type=int, default=150, help="Reject incomplete exports (default: 150)")
    parser.add_argument("--identity-map", type=Path, help="Reviewed JSON source-key to player-ID overrides")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    if args.csv and args.snapshot_date is None:
        parser.error("--csv requires --snapshot-date")
    if args.directory and args.snapshot_date is not None:
        parser.error("--directory derives the source date from the filename; omit --snapshot-date")
    if args.directory:
        path, snapshot_date = newest_pff_csv(args.directory)
    else:
        path, snapshot_date = args.csv, args.snapshot_date
    overrides = None
    if args.identity_map:
        overrides = json.loads(args.identity_map.read_text(encoding="utf-8-sig"))
        if not isinstance(overrides, dict) or not all(
            isinstance(key, str) and isinstance(value, str) and value for key, value in overrides.items()
        ):
            parser.error("Identity map must be a JSON object mapping source keys to existing player IDs")
    with SessionLocal() as session:
        report = import_pff_csv(
            session, path, draft_year=args.draft_year, snapshot_date=snapshot_date,
            min_prospects=args.min_prospects, overrides=overrides, commit=args.commit,
        )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
