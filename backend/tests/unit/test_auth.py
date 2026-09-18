"""Tests for the account and authentication foundation."""

import pytest
import jwt

from app.core.config import settings
from app.core.security import decode_access_token, hash_password, validate_password, verify_password
from app.services.user_service import authenticate_user, register_user


def test_password_hashing_verifies_plaintext() -> None:
    """Password hashing should produce a verifiable digest."""
    plain = "StrongP@ssw0rd!"
    hashed = hash_password(plain)

    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_register_and_authenticate_user() -> None:
    """A user should be able to register and authenticate with valid credentials."""
    created = register_user(
        email="mock.user@example.com",
        password="StrongP@ssw0rd!",
        first_name="Mock",
        last_name="User",
    )

    assert created.email == "mock.user@example.com"
    assert created.password_hash != "StrongP@ssw0rd!"

    authenticated = authenticate_user(
        email="mock.user@example.com",
        password="StrongP@ssw0rd!",
    )

    assert authenticated is not None
    assert authenticated.email == "mock.user@example.com"

    with pytest.raises(ValueError):
        authenticate_user(email="mock.user@example.com", password="wrong-password")


def test_password_policy_requires_complexity() -> None:
    with pytest.raises(ValueError, match="12 characters"):
        validate_password("Short1!")

    with pytest.raises(ValueError, match="upper- and lowercase"):
        validate_password("alllowercase1!")

    with pytest.raises(ValueError, match="number and a special"):
        validate_password("NoNumberSpecial")


def test_access_token_rejects_wrong_audience() -> None:
    token = jwt.encode(
        {"sub": "user-1", "iss": settings.jwt_issuer, "aud": "wrong-client"},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(ValueError, match="Invalid or expired"):
        decode_access_token(token)
