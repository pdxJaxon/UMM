"""Team model for NFL franchise information."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Team:
    """Represents an NFL franchise tracked in the mock draft system."""

    id: str
    name: str
    city: str
    abbreviation: str
    draft_order: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
