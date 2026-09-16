"""User model for the account domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class User:
    """Represents an authenticated user of the platform."""

    id: str
    email: str
    password_hash: str
    first_name: str
    last_name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
