"""Read year-specific reviewed orders without changing legacy seed data."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LeagueDataRefreshRecord, TeamRecord


def latest_league_refresh(session: Session, draft_year: int) -> LeagueDataRefreshRecord | None:
    return session.scalar(select(LeagueDataRefreshRecord).where(
        LeagueDataRefreshRecord.draft_year == draft_year,
    ).order_by(LeagueDataRefreshRecord.reviewed_on.desc(), LeagueDataRefreshRecord.applied_at.desc()).limit(1))


def draft_order_for_year(session: Session, draft_year: int) -> list[str]:
    refresh = latest_league_refresh(session, draft_year)
    if refresh is not None:
        return list(refresh.manifest["draft_order"])
    return list(session.scalars(select(TeamRecord.id).order_by(TeamRecord.draft_order)))
