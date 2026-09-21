"""Scheduling boundary for weekly prospect data refreshes."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.services.prospect_ingestion import ProspectIngestionService, ProspectProvider
from app.services.trade_history import DraftTradeHistoryIngestionService, NflverseDraftTradeHistoryProvider


def run_weekly_refresh(session: Session, provider: ProspectProvider, draft_year: int) -> int:
    """Run one idempotent weekly provider refresh for the requested draft year."""
    return ProspectIngestionService(session, provider).refresh(draft_year, datetime.now(UTC))


def run_weekly_trade_history_refresh(session: Session, provider, seasons: list[int]) -> int:
    """Refresh historical trade events and aggregate team trade tendencies."""
    return DraftTradeHistoryIngestionService(
        session,
        NflverseDraftTradeHistoryProvider(provider),
    ).refresh(seasons, datetime.now(UTC))