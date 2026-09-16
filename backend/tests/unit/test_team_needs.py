"""Tests for season-specific NFL team needs."""

from app.services.ranking_service import calculate_team_need_score


def test_critical_starting_quarterback_need_is_highest() -> None:
    """A critical starter need should outrank a lower-scored depth need."""
    needs = [
        {"position_code": "QB", "role_level": "starter", "need_score": 100},
        {"position_code": "WR", "role_level": "depth", "need_score": 45},
    ]

    assert calculate_team_need_score(needs, "QB") == 100
    assert calculate_team_need_score(needs, "WR") == 45


def test_multiple_same_position_needs_use_diminishing_returns() -> None:
    """Starter and backup needs should both count without double-counting the position."""
    needs = [
        {"position_code": "WR", "need_score": 90},
        {"position_code": "WR", "need_score": 60},
    ]

    assert calculate_team_need_score(needs, "WR") == 100.0


def test_inactive_need_is_ignored_and_position_alias_is_supported() -> None:
    """Inactive records should not affect current draft logic."""
    needs = [
        {"position_code": "OG", "need_score": 95, "is_active": True},
        {"position_code": "IOL", "need_score": 95, "is_active": False},
    ]

    assert calculate_team_need_score(needs, "IOL") == 95