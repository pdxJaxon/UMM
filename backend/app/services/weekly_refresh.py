"""Scheduling boundary for weekly prospect data refreshes."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.services.prospect_ingestion import ProspectIngestionService, ProspectProvider


def run_weekly_refresh(session: Session, provider: ProspectProvider, draft_year: int) -> int:
    """Run one idempotent weekly provider refresh for the requested draft year."""
    return ProspectIngestionService(session, provider).refresh(draft_year, datetime.now(UTC))