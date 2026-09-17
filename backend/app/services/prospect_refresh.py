"""Weekly multi-source prospect refresh orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.prospect_ingestion import ProspectIngestionService, ProspectProvider


class CompositeProspectProvider:
    """Merge normalized records from multiple approved prospect providers."""

    def __init__(self, providers: Iterable[ProspectProvider]) -> None:
        """Create a composite provider in source-priority order."""
        self.providers = tuple(providers)

    def fetch(self, draft_year: int) -> list[dict[str, Any]]:
        """Fetch providers in order and merge records by player ID."""
        merged: dict[str, dict[str, Any]] = {}
        for provider in self.providers:
            for record in provider.fetch(draft_year):
                player_id = str(record["id"])
                current = merged.setdefault(player_id, {})
                _merge_record(current, record)
        return list(merged.values())


def run_weekly_prospect_refresh(
    session: Session,
    draft_year: int,
    providers: Iterable[ProspectProvider],
    observed_at: datetime | None = None,
) -> int:
    """Run one weekly multi-source prospect refresh transaction."""
    composite = CompositeProspectProvider(providers)
    return ProspectIngestionService(session, composite).refresh(draft_year, observed_at)


def _merge_record(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Merge non-empty provider fields while preserving source snapshots."""
    for key, value in incoming.items():
        if key == "measurements":
            existing = target.setdefault("measurements", {})
            existing.update({field: field_value for field, field_value in value.items() if field_value is not None})
        elif key == "athletic_scores":
            target.setdefault("athletic_scores", []).extend(value or [])
        elif value not in (None, ""):
            target[key] = value
