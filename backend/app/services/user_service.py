"""User-related service logic for registration and authentication."""

from __future__ import annotations

from app.core.security import hash_password, verify_password
from app.models.user import User

_USERS: dict[str, User] = {}


def register_user(email: str, password: str, first_name: str, last_name: str) -> User:
    """Create and persist a new user in memory for the current backend runtime."""
    normalized_email = email.strip().lower()
    if not normalized_email or "@" not in normalized_email:
        raise ValueError("A valid email address is required")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    if normalized_email in _USERS:
        raise ValueError("User already exists")

    user = User(
        id=f"user-{len(_USERS) + 1}",
        email=normalized_email,
        password_hash=hash_password(password),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
    )
    _USERS[normalized_email] = user
    return user


def authenticate_user(email: str, password: str) -> User:
    """Validate login credentials and return the matching user record."""
    normalized_email = email.strip().lower()
    user = _USERS.get(normalized_email)
    if user is None:
        raise ValueError("User not found")
    if not verify_password(password, user.password_hash):
        raise ValueError("Invalid credentials")
    return user
