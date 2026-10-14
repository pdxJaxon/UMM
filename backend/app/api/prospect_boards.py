"""Authenticated, read-only review of imported source snapshots."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.models import (
    PlayerRecord, ProspectBoardRankingRecord, ProspectBoardSnapshotRecord, UserRecord,
)
from app.db.session import get_db
from app.services.pff_snapshot import SOURCE_NAME

router = APIRouter(prefix="/api/prospect-boards", tags=["prospect-boards"])


class SnapshotSummary(BaseModel):
    id: str
    collected_at: datetime
    source_updated_at_display: str | None
    source_url: str
    prospect_count: int
    scope: str


class ProspectReviewRow(BaseModel):
    player_id: str
    name: str
    school: str
    source_position: str
    canonical_position: str
    overall_rank: int
    previous_rank: int | None
    rank_change: int | None
    pff_grade: float | None
    eligibility_status: str


class ProspectBoardReview(BaseModel):
    source: str
    draft_year: int
    snapshot: SnapshotSummary | None
    previous_snapshot: SnapshotSummary | None
    entries: list[ProspectReviewRow]


def summarize(snapshot: ProspectBoardSnapshotRecord) -> SnapshotSummary:
    return SnapshotSummary(
        id=snapshot.id, collected_at=snapshot.collected_at.replace(tzinfo=UTC),
        source_updated_at_display=snapshot.source_updated_at_display,
        source_url=snapshot.source_url, prospect_count=snapshot.prospect_count, scope=snapshot.scope,
    )


@router.get("/pff/latest", response_model=ProspectBoardReview)
def latest_pff_board(
    draft_year: int = Query(..., ge=2020, le=2100),
    session: Session = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
) -> ProspectBoardReview:
    """Compare the latest two collected season snapshots by stable player ID."""
    snapshots = session.scalars(
        select(ProspectBoardSnapshotRecord)
        .where(
            ProspectBoardSnapshotRecord.source_name == SOURCE_NAME,
            ProspectBoardSnapshotRecord.draft_year == draft_year,
        )
        .order_by(
            ProspectBoardSnapshotRecord.collected_at.desc(),
            ProspectBoardSnapshotRecord.id.desc(),
        )
        .limit(2)
    ).all()
    if not snapshots:
        return ProspectBoardReview(
            source=SOURCE_NAME, draft_year=draft_year, snapshot=None, previous_snapshot=None, entries=[],
        )
    latest = snapshots[0]
    previous = snapshots[1] if len(snapshots) > 1 else None
    previous_ranks = dict(session.execute(
        select(ProspectBoardRankingRecord.player_id, ProspectBoardRankingRecord.overall_rank)
        .where(ProspectBoardRankingRecord.snapshot_id == previous.id)
    ).all()) if previous is not None else {}
    rows = session.execute(
        select(ProspectBoardRankingRecord, PlayerRecord)
        .join(PlayerRecord, PlayerRecord.id == ProspectBoardRankingRecord.player_id)
        .where(ProspectBoardRankingRecord.snapshot_id == latest.id)
        .order_by(ProspectBoardRankingRecord.overall_rank)
    ).all()
    entries = []
    for ranking, player in rows:
        old_rank = previous_ranks.get(ranking.player_id)
        entries.append(ProspectReviewRow(
            player_id=ranking.player_id, name=ranking.source_name_display,
            school=ranking.source_school, source_position=ranking.source_position,
            canonical_position=ranking.canonical_position, overall_rank=ranking.overall_rank,
            previous_rank=old_rank,
            rank_change=old_rank - ranking.overall_rank if old_rank is not None else None,
            pff_grade=float(ranking.pff_grade) if ranking.pff_grade is not None else None,
            eligibility_status=player.eligibility_status,
        ))
    return ProspectBoardReview(
        source=SOURCE_NAME, draft_year=draft_year, snapshot=summarize(latest),
        previous_snapshot=summarize(previous) if previous is not None else None, entries=entries,
    )
