"""Explicit snapshot approval and shared projected mock-draft availability."""

from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import PlayerRecord, ProspectBoardRankingRecord, ProspectBoardSnapshotRecord


def latest_projected_snapshot(session: Session, draft_year: int) -> ProspectBoardSnapshotRecord | None:
    """Choose the newest explicitly approved source snapshot for new boards/drafts."""
    return session.scalar(select(ProspectBoardSnapshotRecord).where(
        ProspectBoardSnapshotRecord.draft_year == draft_year,
        ProspectBoardSnapshotRecord.projected_pool_approved_at.is_not(None),
    ).order_by(
        ProspectBoardSnapshotRecord.collected_at.desc(),
        ProspectBoardSnapshotRecord.projected_pool_approved_at.desc(),
        ProspectBoardSnapshotRecord.id,
    ).limit(1))


def approve_projected_snapshot(session: Session, snapshot_id: str) -> ProspectBoardSnapshotRecord:
    """Approve one imported snapshot without modifying player eligibility or boards."""
    snapshot = session.get(ProspectBoardSnapshotRecord, snapshot_id)
    if snapshot is None:
        raise ValueError("Prospect snapshot does not exist")
    rankings = list(session.scalars(select(ProspectBoardRankingRecord).where(
        ProspectBoardRankingRecord.snapshot_id == snapshot.id,
    )))
    if not rankings or len(rankings) != snapshot.prospect_count:
        raise ValueError("Snapshot rankings are incomplete")
    if snapshot.projected_pool_approved_at is None:
        snapshot.projected_pool_approved_at = datetime.now(UTC).replace(tzinfo=None)
        session.flush()
    return snapshot


def pool_filter(draft_year: int, snapshot_id: str | None) -> ColumnElement[bool]:
    """Use the selected approved pool, or preserve legacy confirmed-only behavior."""
    if snapshot_id is None:
        return and_(
            PlayerRecord.draft_year == draft_year,
            PlayerRecord.eligibility_status == "eligible",
        )
    membership = select(ProspectBoardRankingRecord.player_id).join(
        ProspectBoardSnapshotRecord,
        ProspectBoardSnapshotRecord.id == ProspectBoardRankingRecord.snapshot_id,
    ).where(
        ProspectBoardRankingRecord.snapshot_id == snapshot_id,
        ProspectBoardSnapshotRecord.draft_year == draft_year,
        ProspectBoardSnapshotRecord.projected_pool_approved_at.is_not(None),
    )
    return and_(
        PlayerRecord.draft_year == draft_year,
        PlayerRecord.eligibility_status.in_(("eligible", "unconfirmed")),
        PlayerRecord.id.in_(membership),
    )


def snapshot_rankings(session: Session, snapshot_id: str | None) -> dict[str, ProspectBoardRankingRecord]:
    """Load ranks from a pinned snapshot, never from arbitrary newer imports."""
    if snapshot_id is None:
        return {}
    return {row.player_id: row for row in session.scalars(
        select(ProspectBoardRankingRecord).where(ProspectBoardRankingRecord.snapshot_id == snapshot_id)
    )}
