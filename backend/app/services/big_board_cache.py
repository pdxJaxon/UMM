"""Cache services for LLM-generated team big boards."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any, Protocol

from redis import Redis

from app.core.config import settings


class BigBoardCache(Protocol):
    """Protocol implemented by production and test big-board caches."""

    def get(self, team_id: str, draft_year: int, board_version: str) -> dict[str, Any] | None:
        """Return a cached board or ``None`` when no entry exists."""

    def set(
        self,
        team_id: str,
        draft_year: int,
        board_version: str,
        board: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a board with an expiration time."""

    def delete(self, team_id: str, draft_year: int, board_version: str) -> None:
        """Remove a cached board entry."""


def build_big_board_cache_key(team_id: str, draft_year: int, board_version: str) -> str:
    """Build a namespaced cache key that isolates board versions and draft years."""
    safe_version = board_version.replace(" ", "_")
    return f"umockme:big-board:{draft_year}:{team_id}:{safe_version}"


class RedisBigBoardCache:
    """Redis-backed cache for sharing generated boards across API workers."""

    def __init__(self, client: Redis[str] | None = None) -> None:
        """Create a cache using the configured Redis URL unless a client is supplied."""
        self.client = client or Redis.from_url(settings.redis_url, decode_responses=True)

    def get(self, team_id: str, draft_year: int, board_version: str) -> dict[str, Any] | None:
        """Deserialize and return a cached board from Redis."""
        value = self.client.get(build_big_board_cache_key(team_id, draft_year, board_version))
        return json.loads(value) if value is not None else None

    def set(
        self,
        team_id: str,
        draft_year: int,
        board_version: str,
        board: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """Serialize and store a board in Redis with a bounded TTL."""
        ttl = ttl_seconds or settings.big_board_cache_ttl_seconds
        if ttl <= 0:
            raise ValueError("Cache TTL must be greater than zero")
        self.client.setex(
            build_big_board_cache_key(team_id, draft_year, board_version),
            ttl,
            json.dumps(board, separators=(",", ":"), sort_keys=True),
        )

    def delete(self, team_id: str, draft_year: int, board_version: str) -> None:
        """Delete a board from Redis when its source inputs change."""
        self.client.delete(build_big_board_cache_key(team_id, draft_year, board_version))


class InMemoryBigBoardCache:
    """Deterministic cache adapter for unit tests and local development."""

    def __init__(self, store: MutableMapping[str, dict[str, Any]] | None = None) -> None:
        """Create an in-memory cache, optionally backed by a supplied mapping."""
        self.store = store if store is not None else {}

    def get(self, team_id: str, draft_year: int, board_version: str) -> dict[str, Any] | None:
        """Return a defensive copy of a cached board."""
        board = self.store.get(build_big_board_cache_key(team_id, draft_year, board_version))
        return json.loads(json.dumps(board)) if board is not None else None

    def set(
        self,
        team_id: str,
        draft_year: int,
        board_version: str,
        board: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a defensive copy of a generated board."""
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("Cache TTL must be greater than zero")
        self.store[build_big_board_cache_key(team_id, draft_year, board_version)] = json.loads(json.dumps(board))

    def delete(self, team_id: str, draft_year: int, board_version: str) -> None:
        """Remove a board from the in-memory cache."""
        self.store.pop(build_big_board_cache_key(team_id, draft_year, board_version), None)