"""Player model for draft prospect information."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Player:
    """Represents a draft prospect and their core profile metadata."""

    id: str
    first_name: str
    last_name: str
    position: str
    college_id: str
    draft_year: int
    eligibility_status: str = "eligible"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
