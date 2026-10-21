"""Preview or apply the supplied 2027 NFL team-needs CSV."""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PlayerRecord, TeamBoardRecord, TeamNeedRecord, TeamRecord
from app.db.session import SessionLocal
from app.services.draft_order import latest_league_refresh
from app.services.prospect_pool import latest_projected_snapshot, pool_filter
from app.services.team_board_service import DRAFT_SCORING_VERSION, generate_persisted_team_board

DRAFT_YEAR = 2027
SOURCE_NAME = "UMockMe issue 44 team-needs CSV"
SOURCE_URL = "https://github.com/user-attachments/files/33787032/Untitled.spreadsheet.-.Sheet1.csv"
CSV_POSITIONS = {
    "QB": ("QB", "quarterback"),
    "RB": ("RB", "running-back"),
    "WR": ("WR", "wide-receiver"),
    "TE": ("TE", "tight-end"),
    "OT": ("OT", "offensive-tackle"),
    "OG": ("IOL", "offensive-guard"),
    "OC": ("IOL", "offensive-center"),
    "DT": ("DT", "defensive-tackle"),
    "Edge": ("EDGE", "edge"),
    "LB": ("LB", "linebacker"),
    "CB": ("CB", "cornerback"),
    "S": ("S", "safety"),
}
TEAM_ALIASES = {
    "cardinals": "team-1",
    "falcons": "team-2",
    "ravens": "team-3",
    "bills": "team-4",
    "panthers": "team-5",
    "bears": "team-6",
    "bengals": "team-7",
    "browns": "team-8",
    "cowboys": "team-9",
    "broncos": "team-10",
    "lions": "team-11",
    "packers": "team-12",
    "texans": "team-13",
    "colts": "team-14",
    "jaguars": "team-15",
    "chiefs": "team-16",
    "raiders": "team-17",
    "chargers": "team-18",
    "rams": "team-19",
    "dolphins": "team-20",
    "vikings": "team-21",
    "patriots": "team-22",
    "saints": "team-23",
    "giants": "team-24",
    "jets": "team-25",
    "eagles": "team-26",
    "steelers": "team-27",
    "forty niners": "team-28",
    "49ers": "team-28",
    "seahawks": "team-29",
    "buccaneers": "team-30",
    "titans": "team-31",
    "commanders": "team-32",
    "redskins": "team-32",
}
def parse_team_needs_csv(contents: str) -> list[dict[str, object]]:
    """Validate the complete source CSV and normalize its 0-10 ratings to 0-100."""
    expected_headers = ["TEAM", *CSV_POSITIONS]
    reader = csv.DictReader(contents.splitlines())
    if reader.fieldnames != expected_headers:
        raise ValueError(f"CSV headers must be exactly: {', '.join(expected_headers)}")

    parsed: list[dict[str, object]] = []
    seen_teams: set[str] = set()
    for line_number, row in enumerate(reader, start=2):
        if None in row:
            raise ValueError(f"Unexpected extra columns on line {line_number}")
        team_name = (row.get("TEAM") or "").strip().casefold()
        team_id = TEAM_ALIASES.get(team_name)
        if team_id is None:
            raise ValueError(f"Unknown team on line {line_number}: {row.get('TEAM')!r}")
        if team_id in seen_teams:
            raise ValueError(f"Duplicate team on line {line_number}: {row.get('TEAM')!r}")
        seen_teams.add(team_id)
        for source_position, (position_code, role_level) in CSV_POSITIONS.items():
            raw_score = (row.get(source_position) or "").strip()
            try:
                source_score = int(raw_score)
            except ValueError as exc:
                raise ValueError(f"Invalid {source_position} score on line {line_number}: {raw_score!r}") from exc
            if not 0 <= source_score <= 10:
                raise ValueError(f"{source_position} score on line {line_number} must be between 0 and 10")
            parsed.append({
                "team_id": team_id,
                "position_code": position_code,
                "role_level": role_level,
                "need_score": source_score * 10,
                "quantity": 1,
                "source_score": source_score,
            })

    if seen_teams != set(TEAM_ALIASES.values()):
        raise ValueError("CSV must contain each of the 32 NFL teams exactly once")
    if len(parsed) != 32 * len(CSV_POSITIONS):
        raise ValueError("CSV must contain exactly 32 complete team rows")
    return parsed


def import_2027_team_needs(
    session: Session,
    contents: str,
    *,
    commit: bool = False,
) -> dict[str, object]:
    """Replace 2027 needs and regenerate default boards in one transaction."""
    needs = parse_team_needs_csv(contents)
    db_team_ids = set(session.scalars(select(TeamRecord.id)))
    if len(db_team_ids) != 32 or db_team_ids != set(TEAM_ALIASES.values()):
        raise ValueError("Database must contain all 32 canonical NFL teams before importing needs")

    snapshot = latest_projected_snapshot(session, DRAFT_YEAR)
    if snapshot is None:
        raise ValueError("Import requires an approved projected-prospect snapshot for 2027")
    available_count = session.scalar(
        select(func.count(PlayerRecord.id)).where(pool_filter(DRAFT_YEAR, snapshot.id))
    ) or 0
    if available_count < 32:
        raise ValueError("Import requires at least 32 available prospects in the approved 2027 snapshot")

    refresh = latest_league_refresh(session, DRAFT_YEAR)
    if refresh is not None:
        draft_order = list(refresh.manifest["draft_order"])
    else:
        draft_order = list(session.scalars(select(TeamRecord.id).order_by(TeamRecord.draft_order)))
    if set(draft_order) != db_team_ids or len(draft_order) != 32:
        raise ValueError("The current 2027 draft order must contain all 32 teams exactly once")

    parsed_values = {
        (str(row["team_id"]), str(row["position_code"]), str(row["role_level"])): float(row["need_score"])
        for row in needs
    }
    existing = session.scalars(select(TeamNeedRecord).where(
        TeamNeedRecord.draft_year == DRAFT_YEAR,
        TeamNeedRecord.is_active.is_(True),
    )).all()
    existing_values = {
        (row.team_id, row.position_code, row.role_level): float(row.need_score)
        for row in existing
    }
    latest_boards = {
        team_id: session.scalar(
            select(TeamBoardRecord)
            .where(
                TeamBoardRecord.team_id == team_id,
                TeamBoardRecord.draft_year == DRAFT_YEAR,
                TeamBoardRecord.board_type == "default",
                TeamBoardRecord.user_id.is_(None),
            )
            .order_by(TeamBoardRecord.version.desc())
            .limit(1)
        )
        for team_id in db_team_ids
    }
    boards_current = all(
        board is not None and board.scoring_version == DRAFT_SCORING_VERSION
        for board in latest_boards.values()
    )
    needs_current = (
        len(existing) == len(parsed_values)
        and existing_values == parsed_values
        and all(row.source_name == SOURCE_NAME for row in existing)
    )
    if needs_current and boards_current:
        return {"status": "unchanged", "draft_year": DRAFT_YEAR, "teams": 32, "need_rows": len(needs)}

    report: dict[str, object] = {
        "status": "applied" if commit else "dry_run",
        "draft_year": DRAFT_YEAR,
        "teams": 32,
        "need_rows": len(needs),
        "default_boards_to_generate": 32,
        "prospect_snapshot_id": snapshot.id,
    }
    if not commit:
        return report

    observed_at = datetime.now(UTC).replace(tzinfo=None)
    with session.begin_nested():
        for row in existing:
            row.is_active = False
        for need in needs:
            session.add(TeamNeedRecord(
                team_id=need["team_id"],
                draft_year=DRAFT_YEAR,
                position_code=need["position_code"],
                role_level=need["role_level"],
                need_score=need["need_score"],
                quantity=need["quantity"],
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                rationale=f"Source CSV need score: {need['source_score']}/10.",
                observed_at=observed_at,
            ))
        session.flush()
        for pick_number, team_id in enumerate(draft_order, start=1):
            generate_persisted_team_board(
                session, team_id, DRAFT_YEAR, pick_number=pick_number, commit=False,
            )
    session.commit()
    report.pop("default_boards_to_generate")
    report["default_boards_generated"] = 32
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the reviewed 2027 NFL team-needs CSV; dry-run by default")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    contents = args.csv.read_text(encoding="utf-8-sig")
    with SessionLocal() as session:
        report = import_2027_team_needs(session, contents, commit=args.commit)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
