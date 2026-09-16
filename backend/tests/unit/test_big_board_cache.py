"""Tests for generated team big-board caching."""

from unittest.mock import Mock

import pytest

from app.services.big_board_cache import (
    InMemoryBigBoardCache,
    RedisBigBoardCache,
    build_big_board_cache_key,
)


def test_cache_key_is_versioned_by_team_year_and_board_version() -> None:
    """Different board inputs must never collide in the cache namespace."""
    assert build_big_board_cache_key("team-1", 2026, "llm-v1") == "umockme:big-board:2026:team-1:llm-v1"


def test_in_memory_cache_round_trip_isolated_from_mutations() -> None:
    """Cached results should not be mutated by callers after retrieval."""
    cache = InMemoryBigBoardCache()
    board = {"players": [{"player_id": "player-1", "rank": 1}], "model": "llm-v1"}

    cache.set("team-1", 2026, "llm-v1", board)
    board["players"][0]["rank"] = 99

    assert cache.get("team-1", 2026, "llm-v1")["players"][0]["rank"] == 1
    cache.delete("team-1", 2026, "llm-v1")
    assert cache.get("team-1", 2026, "llm-v1") is None


def test_redis_cache_serializes_board_and_applies_ttl() -> None:
    """Redis storage should use JSON and the configured expiration."""
    client = Mock()
    cache = RedisBigBoardCache(client)
    board = {"players": ["player-1"], "model": "llm-v1"}

    cache.set("team-1", 2026, "llm-v1", board, ttl_seconds=900)
    client.setex.assert_called_once_with(
        "umockme:big-board:2026:team-1:llm-v1",
        900,
        '{"model":"llm-v1","players":["player-1"]}',
    )

    client.get.return_value = '{"model":"llm-v1","players":["player-1"]}'
    assert cache.get("team-1", 2026, "llm-v1") == board


def test_cache_rejects_non_positive_ttl() -> None:
    """Cache entries must not be configured to expire immediately or never."""
    with pytest.raises(ValueError, match="greater than zero"):
        InMemoryBigBoardCache().set("team-1", 2026, "llm-v1", {}, ttl_seconds=0)