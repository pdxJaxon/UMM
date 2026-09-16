"""Security utilities for password hashing and validation."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    """Hash a plaintext password using a unique PBKDF2 salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a password matches its stored PBKDF2 hash."""
    try:
        salt_hex, digest_hex = password_hash.split("$", maxsplit=1)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(subject: str) -> str:
    """Create a short-lived signed JWT for an authenticated user."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """Validate a JWT and return its user subject."""
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid or expired access token") from exc
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise ValueError("Access token subject is missing")
    return subject
