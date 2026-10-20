"""Read authorized local PFF candidate exports without enriching player profiles."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime, time
from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProspectBoardSnapshotRecord
from app.services.pff_snapshot import PFFBoardSnapshot, PFFProspectRow, SOURCE_NAME
from app.services.prospect_board_import import import_board_snapshot

COLUMNS = ("Rank", "Player", "Position", "School", "PFF Grade", "Analysis")
FILE_PATTERN = re.compile(r"pff-my-big-board-(\d{4}-\d{2}-\d{2})\.csv")


def read_pff_csv(
    path: str | Path, *, draft_year: int, snapshot_date: date,
) -> PFFBoardSnapshot:
    """Validate all candidate rows; do not store the export's narrative analysis."""
    if snapshot_date > datetime.now(UTC).date():
        raise ValueError("PFF snapshot date cannot be in the future")
    prospects: list[PFFProspectRow] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames is None or tuple(reader.fieldnames) != COLUMNS:
            raise ValueError(f"PFF CSV headers must be exactly: {', '.join(COLUMNS)}")
        try:
            for row in reader:
                if None in row or any(row.get(column) is None for column in COLUMNS):
                    raise ValueError(f"PFF CSV row {reader.line_num} has missing or extra fields")
                if any(not row[column].strip() for column in ("Rank", "Player", "Position", "School")):
                    raise ValueError(f"PFF CSV row {reader.line_num} has missing candidate fields")
                rank = row["Rank"].strip()
                if not rank.isascii() or not rank.isdecimal():
                    raise ValueError(f"PFF CSV row {reader.line_num} has an invalid rank")
                grade = row["PFF Grade"].strip()
                try:
                    prospects.append(PFFProspectRow(
                        overall_rank=int(rank), name=row["Player"], position=row["Position"],
                        school=row["School"], pff_grade=float(grade) if grade else None,
                    ))
                except ValueError as error:
                    raise ValueError(f"Invalid PFF candidate at CSV row {reader.line_num}: {error}") from error
        except csv.Error as error:
            raise ValueError(f"Invalid PFF CSV near row {reader.line_num}: {error}") from error
    return PFFBoardSnapshot(
        source_url=f"https://www.pff.com/draft/big-board?season={draft_year}",
        draft_year=draft_year, collected_at=datetime.combine(snapshot_date, time.min, tzinfo=UTC),
        source_updated_at_display=snapshot_date.isoformat(),
        collection_method="authorized user-provided PFF CSV",
        scope=f"All {len(prospects)} candidates in supplied export; eligibility is unconfirmed",
        prospects=tuple(prospects),
    )


def newest_pff_csv(directory: Path) -> tuple[Path, date]:
    """Select by the explicit export date, never file modification timestamps."""
    if not directory.is_dir():
        raise ValueError(f"PFF inbox directory does not exist: {directory}")
    candidates = []
    for path in directory.glob("pff-my-big-board-*.csv"):
        match = FILE_PATTERN.fullmatch(path.name)
        if match is None or not path.is_file():
            raise ValueError(f"Invalid PFF export filename: {path.name}")
        try:
            source_date = date.fromisoformat(match[1])
        except ValueError as error:
            raise ValueError(f"Invalid date in PFF export filename: {path.name}") from error
        if source_date > datetime.now(UTC).date():
            raise ValueError(f"Future-dated PFF export requires review: {path.name}")
        candidates.append((path, source_date))
    if not candidates:
        raise ValueError(f"No pff-my-big-board-YYYY-MM-DD.csv exports found in {directory}")
    return max(candidates, key=lambda candidate: candidate[1])


def import_pff_csv(
    session: Session, path: Path, *, draft_year: int, snapshot_date: date,
    min_prospects: int = 150, overrides: dict[str, str] | None = None, commit: bool = False,
) -> dict[str, object]:
    """Import only a newer validated PFF snapshot, keeping approval separate."""
    if min_prospects < 1:
        raise ValueError("Minimum prospect count must be positive")
    snapshot = read_pff_csv(path, draft_year=draft_year, snapshot_date=snapshot_date)
    if len(snapshot.prospects) < min_prospects:
        raise ValueError(f"PFF CSV has {len(snapshot.prospects)} candidates; at least {min_prospects} required")
    existing = session.scalar(select(ProspectBoardSnapshotRecord).where(
        ProspectBoardSnapshotRecord.content_hash == snapshot.content_hash(),
    ))
    latest = session.scalar(select(ProspectBoardSnapshotRecord).where(
        ProspectBoardSnapshotRecord.source_name == SOURCE_NAME,
        ProspectBoardSnapshotRecord.draft_year == draft_year,
    ).order_by(ProspectBoardSnapshotRecord.collected_at.desc()).limit(1))
    if existing is not None:
        report = import_board_snapshot(session, snapshot, overrides, commit=commit)
    elif latest is not None and latest.collected_at.date() > snapshot_date:
        report = {"status": "skipped_older", "snapshot_id": latest.id}
    elif latest is not None and latest.collected_at.date() == snapshot_date:
        raise ValueError("Different PFF data already exists for this date; review the correction manually")
    else:
        report = import_board_snapshot(session, snapshot, overrides, commit=commit)
    return {
        **report, "file": path.name, "source": SOURCE_NAME, "snapshot_date": snapshot_date.isoformat(),
        "draft_year": draft_year, "projected_pool_approval": "manual",
        "full_refresh_date_unchanged": True,
    }
