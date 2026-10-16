"""Strict CSV adapter for dated consensus prospect boards."""

from __future__ import annotations

import csv
from datetime import date, datetime, time, UTC
from pathlib import Path
from typing import ClassVar

from app.services.pff_snapshot import BoardSnapshot, POSITION_MAP, ProspectRow

SOURCE_NAME = "consensus-big-board"
COLUMNS = ("Rank", "Player Name", "Position", "College")


class ConsensusBoardSnapshot(BoardSnapshot):
    """Consensus source ranks kept separate from UMM scoring and eligibility."""

    source: str = SOURCE_NAME
    position_map: ClassVar[dict[str, str]] = {**POSITION_MAP, "DL": "DT"}


def read_consensus_csv(
    path: str | Path,
    *,
    draft_year: int,
    snapshot_date: date,
    limit: int | None = None,
) -> ConsensusBoardSnapshot:
    """Validate the file structure and identities, then map the selected ranks."""
    if limit is not None and limit < 1:
        raise ValueError("Prospect limit must be greater than zero")
    source = Path(path)
    prospects: list[ProspectRow] = []
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames is None or set(reader.fieldnames) != set(COLUMNS) or len(reader.fieldnames) != len(COLUMNS):
            raise ValueError(f"CSV headers must be exactly: {', '.join(COLUMNS)}")
        try:
            for row in reader:
                if None in row or any(row.get(column) is None or not row[column].strip() for column in COLUMNS):
                    raise ValueError(f"CSV row {reader.line_num} has missing or extra fields")
                rank = row["Rank"].strip()
                if not rank.isascii() or not rank.isdecimal():
                    raise ValueError(f"CSV row {reader.line_num} has an invalid rank: {rank!r}")
                prospects.append(ProspectRow(
                    overall_rank=int(rank), name=row["Player Name"],
                    position=row["Position"], school=row["College"],
                ))
        except csv.Error as error:
            raise ValueError(f"Invalid CSV near row {reader.line_num}: {error}") from error
    ranks = [row.overall_rank for row in prospects]
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        raise ValueError("Ranks must be unique and consecutive starting at 1")
    if len({row.key for row in prospects}) != len(prospects):
        raise ValueError("Duplicate source identities in CSV")
    if limit is not None and len(prospects) < limit:
        raise ValueError(f"Requested {limit} prospects but CSV contains only {len(prospects)}")
    selected = sorted(prospects, key=lambda row: row.overall_rank)
    if limit is not None:
        selected = selected[:limit]
    return ConsensusBoardSnapshot(
        source_url=source.resolve().as_uri(),
        draft_year=draft_year,
        collected_at=datetime.combine(snapshot_date, time.min, tzinfo=UTC),
        source_updated_at_display=snapshot_date.isoformat(),
        collection_method="user-provided consensus CSV",
        scope=f"Top {len(selected)} of {len(prospects)} projected prospects; player status and rankings may change",
        prospects=tuple(selected),
    )
