"""Collect or import permitted PFF browser snapshots; never implicitly mutate data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.pff_browser_collector import collect_board
from app.services.pff_snapshot import PFFBoardSnapshot, load_identity_overrides


def main() -> int:
    """Run a read-only collection or explicitly requested snapshot import."""
    parser = argparse.ArgumentParser(description="Collect/review/import a permitted PFF Big Board snapshot")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="Save validated rendered rows, without database writes")
    collect.add_argument("--draft-year", type=int, required=True)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--min-prospects", type=int, default=32)
    collect.add_argument("--storage-state", type=Path, help="Optional authorized browser session; keep outside git")
    collect.add_argument("--headed", action="store_true")
    collect.add_argument("--cdp-url", help="Attach read-only to an existing authorized local Chromium browser")
    ingest = commands.add_parser("import", help="Validate and preview a local snapshot; dry-run by default")
    ingest.add_argument("--snapshot", type=Path, required=True)
    ingest.add_argument("--identity-map", type=Path, help="Reviewed JSON object: source_key to existing UMM player ID")
    ingest.add_argument("--commit", action="store_true", help="Persist the entire validated snapshot transaction")
    args = parser.parse_args()
    if args.command == "collect":
        if args.output.exists():
            parser.error("Output already exists; choose a new dated snapshot path")
        snapshot = collect_board(
            args.draft_year, args.min_prospects, args.storage_state, args.headed, args.cdp_url,
        )
        with args.output.open("x", encoding="utf-8") as output:
            output.write(snapshot.model_dump_json(indent=2))
        print(json.dumps({
            "status": "collected", "output": str(args.output), "prospect_count": len(snapshot.prospects),
            "missing_grades": sum(row.pff_grade is None for row in snapshot.prospects),
            "source_updated_at_display": snapshot.source_updated_at_display,
        }))
        return 0

    from app.db.session import SessionLocal
    from app.services.prospect_board_import import import_board_snapshot

    snapshot = PFFBoardSnapshot.model_validate_json(args.snapshot.read_text(encoding="utf-8-sig"))
    overrides = None
    if args.identity_map:
        try:
            overrides = load_identity_overrides(args.identity_map)
        except ValueError as exc:
            parser.error(str(exc))
    with SessionLocal() as session:
        report = import_board_snapshot(session, snapshot, overrides, commit=args.commit)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
