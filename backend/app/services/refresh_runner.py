"""Retrying, auditable runner for weekly prospect refreshes."""

from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import ProspectRefreshRunRecord
from app.services.prospect_ingestion import ProspectProvider
from app.services.prospect_refresh import run_weekly_prospect_refresh


def run_refresh_with_retries(
    session: Session,
    draft_year: int,
    providers: Iterable[ProspectProvider],
    max_attempts: int = 3,
    retry_delay_seconds: float = 5.0,
) -> int:
    """Run a refresh with bounded retries and persist a final audit outcome."""
    provider_list = list(providers)
    source_names = [provider.__class__.__name__ for provider in provider_list]
    started_at = datetime.utcnow()
    audit = ProspectRefreshRunRecord(
        draft_year=draft_year,
        status="running",
        attempts=0,
        source_names=source_names,
        started_at=started_at,
    )
    session.add(audit)
    session.commit()

    try:
        for attempt in range(1, max_attempts + 1):
            audit.attempts = attempt
            session.commit()
            try:
                processed = run_weekly_prospect_refresh(session, draft_year, provider_list, started_at)
                audit.status = "succeeded"
                audit.processed_count = processed
                audit.completed_at = datetime.utcnow()
                session.commit()
                return processed
            except Exception as exc:
                session.rollback()
                if attempt == max_attempts:
                    audit = session.get(ProspectRefreshRunRecord, audit.id)
                    audit.status = "failed"
                    audit.completed_at = datetime.utcnow()
                    audit.error_message = str(exc)[:2000]
                    audit.attempts = attempt
                    session.commit()
                    raise
                time.sleep(retry_delay_seconds)
    except Exception:
        raise
    raise RuntimeError("Refresh runner exhausted without an outcome")