"""Configuration helpers for the UMockMe backend."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Application settings used by the backend service layer."""

    app_name: str = "UMockMe"
    environment: str = "development"
    secret_key: str = "dev-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "umockme-api"
    jwt_audience: str = "umockme-client"
    access_token_minutes: int = 30
    cors_origins: tuple[str, ...] = ("http://localhost:4201", "http://127.0.0.1:4201")
    database_url: str = "sqlite:///./umockme.db"
    redis_url: str = "redis://localhost:6379/0"
    big_board_cache_ttl_seconds: int = 3600
    pff_data_url: str = ""
    pff_api_key: str = ""
    pff_request_timeout_seconds: float = 30.0
    pff_big_board_url: str = "https://www.pff.com/draft/big-board"

    @classmethod
    def from_environment(cls) -> "Settings":
        """Build settings from environment variables with local defaults."""
        return cls(
            app_name=os.getenv("APP_NAME", cls.app_name),
            environment=os.getenv("APP_ENV", cls.environment).strip().lower(),
            secret_key=os.getenv("SECRET_KEY", cls.secret_key),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", cls.jwt_algorithm),
            jwt_issuer=os.getenv("JWT_ISSUER", cls.jwt_issuer),
            jwt_audience=os.getenv("JWT_AUDIENCE", cls.jwt_audience),
            access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", str(cls.access_token_minutes))),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("CORS_ORIGINS", ",".join(cls.cors_origins)).split(",")
                if origin.strip()
            ),
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            redis_url=os.getenv("REDIS_URL", cls.redis_url),
            big_board_cache_ttl_seconds=int(
                os.getenv("BIG_BOARD_CACHE_TTL_SECONDS", str(cls.big_board_cache_ttl_seconds))
            ),
            pff_data_url=os.getenv("PFF_DATA_URL", cls.pff_data_url),
            pff_api_key=os.getenv("PFF_API_KEY", os.getenv("PFF_API_TOKEN", cls.pff_api_key)),
            pff_request_timeout_seconds=float(
                os.getenv("PFF_REQUEST_TIMEOUT_SECONDS", str(cls.pff_request_timeout_seconds))
            ),
            pff_big_board_url=os.getenv("PFF_BIG_BOARD_URL", cls.pff_big_board_url),
        )


settings = Settings.from_environment()

if settings.environment in {"production", "prod"}:
    if settings.secret_key == Settings.secret_key or len(settings.secret_key) < 32:
        raise RuntimeError("SECRET_KEY must be configured with at least 32 characters in production")
    if settings.jwt_algorithm != "HS256":
        raise RuntimeError("Only the configured HS256 JWT algorithm is supported")
    if not settings.cors_origins or settings.cors_origins == Settings.cors_origins:
        raise RuntimeError("CORS_ORIGINS must be explicitly configured in production")
