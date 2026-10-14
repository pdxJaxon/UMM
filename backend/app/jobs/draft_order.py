"""Operator-only import/approval; no scraping or implicit schema changes."""

import argparse
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.services.draft_order_snapshots import DraftOrderSnapshot, approve_order, import_order


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview/import or explicitly approve draft pick ownership")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("import")
    ingest.add_argument("--snapshot", type=Path, required=True)
    ingest.add_argument("--commit", action="store_true")
    approve = commands.add_parser("approve")
    approve.add_argument("--snapshot-id", required=True)
    approve.add_argument("--reviewer", required=True)
    args = parser.parse_args()
    with SessionLocal() as session:
        if args.command == "import":
            snapshot = DraftOrderSnapshot.model_validate_json(args.snapshot.read_text(encoding="utf-8-sig"))
            report = import_order(session, snapshot, commit=args.commit)
        else:
            report = approve_order(session, args.snapshot_id, args.reviewer)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
