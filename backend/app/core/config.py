"""Configuration helpers for the UMockMe backend."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Application settings used by the backend service layer."""

    app_name: str = "UMockMe"
    secret_key: str = "dev-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    database_url: str = "postgresql+psycopg://umockme:umockme@localhost:5432/umockme"

    @classmethod
    def from_environment(cls) -> "Settings":
        """Build settings from environment variables with local defaults."""
        return cls(
            app_name=os.getenv("APP_NAME", cls.app_name),
            secret_key=os.getenv("SECRET_KEY", cls.secret_key),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", cls.jwt_algorithm),
            access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", str(cls.access_token_minutes))),
            database_url=os.getenv("DATABASE_URL", cls.database_url),
        )


settings = Settings.from_environment()
