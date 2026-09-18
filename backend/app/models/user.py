"""User model for the account domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class User:
    """Represents an authenticated user of the platform."""

    id: str
    email: str
    password_hash: str
    first_name: str
    last_name: str
    favorite_team_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True
