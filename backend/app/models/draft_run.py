"""Draft run model for a single mock draft session."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional


@dataclass
class DraftRun:
    """Captures a single mock draft simulation session."""

    id: str
    user_id: str
    controlled_team_id: str
    season_year: int
    status: str = "drafting"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = None
