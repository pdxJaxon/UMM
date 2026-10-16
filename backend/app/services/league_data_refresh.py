"""Reviewed, atomic refreshes of year-specific projected order and team needs."""

from datetime import UTC, date, datetime, time
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LeagueDataRefreshRecord, PositionImportanceRecord, TeamNeedRecord, TeamRecord
from app.services.prospect_pool import latest_projected_snapshot, pool_filter
from app.db.models import PlayerRecord
from app.services.team_board_service import generate_persisted_team_board
from app.services.draft_order import latest_league_refresh


class ReviewedSource(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl = Field(max_length=500)
    observed_on: date


class ReviewedNeed(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    position_code: str = Field(min_length=1, max_length=20)
    role_level: str = Field(min_length=1, max_length=30)
    need_score: float = Field(ge=0, le=100, allow_inf_nan=False)
    quantity: int = Field(ge=1, le=10, strict=True)
    rationale: str = Field(min_length=1, max_length=500)


class ReviewedTeamNeeds(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    team_id: str = Field(min_length=1)
    source: ReviewedSource
    needs: list[ReviewedNeed] = Field(min_length=1)


class LeagueRefreshManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    draft_year: int = Field(ge=2020, le=2100, strict=True)
    reviewed_on: date
    reviewed_by: str = Field(min_length=1, max_length=100)
    prospect_snapshot_id: str = Field(min_length=1, max_length=64)
    order_basis: Literal["projected-one-pick-per-team"]
    order_source: ReviewedSource
    draft_order: list[str] = Field(min_length=32, max_length=32)
    team_needs: list[ReviewedTeamNeeds] = Field(min_length=32, max_length=32)

    @model_validator(mode="after")
    def validate_review_dates(self):
        if self.reviewed_on > datetime.now(UTC).date():
            raise ValueError("Review date cannot be in the future")
        if any(source.observed_on > self.reviewed_on for source in [
            self.order_source, *(team.source for team in self.team_needs),
        ]):
            raise ValueError("Source dates cannot be later than the review date")
        return self


def import_league_refresh(
    session: Session, manifest: LeagueRefreshManifest, *, commit: bool = False,
) -> dict[str, object]:
    """Validate before writing; publish needs, audit record, and defaults together."""
    payload = manifest.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    team_ids = set(session.scalars(select(TeamRecord.id)))
    ordered_ids = manifest.draft_order
    needs_ids = [team.team_id for team in manifest.team_needs]
    if len(team_ids) != 32 or set(ordered_ids) != team_ids or set(needs_ids) != team_ids:
        raise ValueError("Order and needs must each cover all 32 canonical team IDs exactly once")
    if len(set(needs_ids)) != 32 or len(set(ordered_ids)) != 32:
        raise ValueError("Duplicate teams are not allowed")
    positions = set(session.scalars(select(PositionImportanceRecord.position_code)))
    for team in manifest.team_needs:
        keys = [(need.position_code, need.role_level) for need in team.needs]
        if len(set(keys)) != len(keys):
            raise ValueError(f"Duplicate position/role need for {team.team_id}")
        if any(need.position_code not in positions for need in team.needs):
            raise ValueError(f"Unknown position code for {team.team_id}; use canonical position codes")
    snapshot = latest_projected_snapshot(session, manifest.draft_year)
    if snapshot is None or snapshot.id != manifest.prospect_snapshot_id:
        raise ValueError("Manifest must reference the latest approved prospect snapshot for this year")
    if snapshot.collected_at.date() > manifest.reviewed_on:
        raise ValueError("Prospect snapshot is later than the review date")
    available = list(session.scalars(select(PlayerRecord.id).where(
        pool_filter(manifest.draft_year, snapshot.id),
    )))
    if len(available) < 32:
        raise ValueError("At least 32 available approved prospects are required")
    latest = latest_league_refresh(session, manifest.draft_year)
    if latest is not None and latest.id != digest and latest.reviewed_on.date() >= manifest.reviewed_on:
        raise ValueError("Replacement refreshes require a later review date")
    existing = session.get(LeagueDataRefreshRecord, digest)
    report = {
        "status": "unchanged" if existing else ("applied" if commit else "dry_run"),
        "refresh_id": digest, "draft_year": manifest.draft_year,
        "order_basis": manifest.order_basis, "teams": 32,
        "need_rows": sum(len(team.needs) for team in manifest.team_needs),
        "prospect_snapshot_id": snapshot.id,
        "personal_boards_unchanged": True, "existing_drafts_unchanged": True,
        "full_refresh_date_unchanged": True,
    }
    if not commit or existing:
        return report
    with session.begin_nested():
        for need in session.scalars(select(TeamNeedRecord).where(
            TeamNeedRecord.draft_year == manifest.draft_year, TeamNeedRecord.is_active.is_(True),
        )):
            need.is_active = False
        for team in manifest.team_needs:
            for need in team.needs:
                session.add(TeamNeedRecord(
                    team_id=team.team_id, draft_year=manifest.draft_year,
                    **need.model_dump(), source_name=team.source.name, source_url=str(team.source.url),
                    observed_at=datetime.combine(team.source.observed_on, time.min),
                ))
        session.add(LeagueDataRefreshRecord(
            id=digest, draft_year=manifest.draft_year,
            reviewed_on=datetime.combine(manifest.reviewed_on, time.min),
            prospect_snapshot_id=snapshot.id, manifest=payload,
        ))
        session.flush()
        for pick_number, team_id in enumerate(ordered_ids, 1):
            generate_persisted_team_board(
                session, team_id, manifest.draft_year, pick_number=pick_number, commit=False,
            )
    session.commit()
    report["default_boards_generated"] = 32
    return report
