"""Tests for the account and authentication foundation."""

import pytest

from app.core.security import hash_password, verify_password
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
