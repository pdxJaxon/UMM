"""Explicit operator approval of a reviewed imported snapshot for mock drafts."""

import argparse
import json

from sqlalchemy import select

from app.db.models import ProspectBoardSnapshotRecord, TeamRecord
from app.db.session import SessionLocal
from app.services.prospect_pool import approve_projected_snapshot, latest_projected_snapshot
from app.services.team_board_service import generate_persisted_team_board


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve one reviewed snapshot for projected mock-draft use")
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--commit", action="store_true", help="Approve this snapshot; otherwise preview only")
    parser.add_argument("--generate-boards", action="store_true", help="Generate new default boards, not personal boards")
    args = parser.parse_args()
    if args.generate_boards and not args.commit:
        parser.error("--generate-boards requires --commit")
    with SessionLocal() as session:
        snapshot = session.get(ProspectBoardSnapshotRecord, args.snapshot_id)
        if snapshot is None:
            parser.error("Snapshot does not exist; import and review it first")
        report = {
            "status": "approved" if args.commit else "dry_run",
            "snapshot_id": snapshot.id, "draft_year": snapshot.draft_year,
            "prospect_count": snapshot.prospect_count, "eligibility_unchanged": True,
        }
        if args.commit:
            approve_projected_snapshot(session, snapshot.id)
            active = latest_projected_snapshot(session, snapshot.draft_year)
            if args.generate_boards and (active is None or active.id != snapshot.id):
                parser.error("A newer snapshot is already approved; cannot generate boards for an older pool")
            session.commit()
            if args.generate_boards:
                team_ids = list(session.scalars(select(TeamRecord.id).order_by(TeamRecord.draft_order)))
                for team_id in team_ids:
                    generate_persisted_team_board(session, team_id, snapshot.draft_year)
                report["default_boards_generated"] = len(team_ids)
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
