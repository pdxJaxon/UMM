"""Validated, explicitly approved pick ownership snapshots."""

from datetime import UTC, datetime
import hashlib
import json
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DraftOrderSnapshotRecord, TeamRecord


class OrderPick(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    overall_pick: int = Field(strict=True, ge=1)
    round_number: int = Field(strict=True, ge=1, le=7)
    owner_team_id: str = Field(min_length=1, max_length=64)
    original_team_id: str | None = Field(default=None, min_length=1, max_length=64)
    details: str | None = Field(default=None, max_length=2000)


class DraftOrderSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    draft_year: int = Field(strict=True, ge=2020, le=2100)
    collected_at: datetime
    source_name: str = Field(min_length=1, max_length=100)
    source_url: str = Field(max_length=500)
    order_status: Literal["projected", "final"]
    scope: Literal["first_round", "full_draft"]
    expected_round_counts: tuple[int, ...]
    picks: tuple[OrderPick, ...] = Field(min_length=1)

    @field_validator("collected_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("Collection timestamp must include a timezone")
        return value.astimezone(UTC)

    @field_validator("source_url")
    @classmethod
    def source_address(cls, value: str) -> str:
        url = urlparse(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("Source URL must be HTTPS without credentials")
        return value

    @model_validator(mode="after")
    def complete_order(self) -> "DraftOrderSnapshot":
        rows = sorted(self.picks, key=lambda row: row.overall_pick)
        if [row.overall_pick for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError("Overall picks must be unique and consecutive starting at 1")
        rounds = [row.round_number for row in rows]
        expected_rounds = [1] if self.scope == "first_round" else list(range(1, 8))
        if sorted(set(rounds)) != expected_rounds or rounds != sorted(rounds):
            raise ValueError("Snapshot scope requires complete, ordered round coverage")
        if (
            len(self.expected_round_counts) != len(expected_rounds)
            or any(type(count) is not int or count < 1 for count in self.expected_round_counts)
            or [rounds.count(number) for number in expected_rounds] != list(self.expected_round_counts)
        ):
            raise ValueError("Pick counts must match independently reviewed expected round counts")
        if any(rounds.count(number) > 32 for number in (1, 2)):
            raise ValueError("Rounds 1 and 2 cannot exceed 32 picks each")
        return self

    def payload(self) -> dict:
        payload = self.model_dump(mode="json")
        payload["picks"] = sorted(payload["picks"], key=lambda row: row["overall_pick"])
        return payload


def import_order(session: Session, snapshot: DraftOrderSnapshot, *, commit: bool = False) -> dict:
    teams = set(session.scalars(select(TeamRecord.id)))
    referenced = {row.owner_team_id for row in snapshot.picks}
    referenced.update(row.original_team_id for row in snapshot.picks if row.original_team_id is not None)
    if referenced - teams:
        raise ValueError(f"Unknown team IDs: {sorted(referenced - teams)}")
    payload = snapshot.payload()
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = session.scalar(select(DraftOrderSnapshotRecord).where(
        DraftOrderSnapshotRecord.content_hash == fingerprint,
    ))
    report = {
        "status": "already_imported" if existing else ("imported" if commit else "dry_run"),
        "snapshot_id": existing.id if existing else "order-" + fingerprint[:48],
        "pick_count": len(snapshot.picks), "approved": existing.approved_at is not None if existing else False,
    }
    if commit and existing is None:
        session.add(DraftOrderSnapshotRecord(
            id=report["snapshot_id"], content_hash=fingerprint, draft_year=snapshot.draft_year,
            collected_at=snapshot.collected_at.replace(tzinfo=None),
            source_name=snapshot.source_name, source_url=snapshot.source_url,
            order_status=snapshot.order_status, scope=snapshot.scope, picks=payload["picks"],
            expected_round_counts=list(snapshot.expected_round_counts),
        ))
        session.commit()
    return report


def approve_order(session: Session, snapshot_id: str, reviewer: str) -> dict:
    reviewer = reviewer.strip()
    if not reviewer or len(reviewer) > 150:
        raise ValueError("A reviewer name of 1-150 characters is required")
    snapshot = session.get(DraftOrderSnapshotRecord, snapshot_id)
    if snapshot is None:
        raise ValueError("Draft-order snapshot not found")
    if snapshot.approved_at is None:
        snapshot.approved_at = datetime.now(UTC).replace(tzinfo=None)
        snapshot.approved_by = reviewer
        session.commit()
    return {"status": "approved", "snapshot_id": snapshot.id, "approved_by": snapshot.approved_by}


def starting_order(session: Session, draft_year: int) -> tuple[list[str], dict]:
    snapshot = session.scalar(
        select(DraftOrderSnapshotRecord)
        .where(DraftOrderSnapshotRecord.draft_year == draft_year, DraftOrderSnapshotRecord.approved_at.is_not(None))
        .order_by(DraftOrderSnapshotRecord.collected_at.desc(), DraftOrderSnapshotRecord.id.desc()).limit(1)
    )
    if snapshot is None:
        teams = list(session.scalars(select(TeamRecord).order_by(TeamRecord.draft_order, TeamRecord.id)))
        return [team.id for team in teams], {
            "kind": "reference_fallback", "label": "Reference team order; no approved season snapshot",
            "starting_order": [team.id for team in teams],
        }
    picks = sorted(
        (row for row in snapshot.picks if row["round_number"] == 1), key=lambda row: row["overall_pick"],
    )
    order = [row["owner_team_id"] for row in picks]
    return order, {
        "kind": "approved_snapshot", "snapshot_id": snapshot.id,
        "source_name": snapshot.source_name, "source_url": snapshot.source_url,
        "collected_at": snapshot.collected_at.replace(tzinfo=UTC).isoformat(),
        "order_status": snapshot.order_status, "starting_order": order.copy(),
        "label": f"{snapshot.order_status.title()} source order",
    }
