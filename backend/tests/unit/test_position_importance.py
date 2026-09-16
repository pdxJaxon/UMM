"""Tests for position importance and ranking integration."""

import pytest

from app.services.ranking_service import (
    calculate_position_adjusted_ranking,
    get_position_importance,
)


def test_quarterback_is_more_important_than_punter() -> None:
    """The baseline should reflect the requested premium-position ordering."""
    assert get_position_importance("QB") > get_position_importance("P")
    assert get_position_importance("P") > get_position_importance("LS")


def test_position_aliases_map_to_position_groups() -> None:
    """Legacy scouting labels should map to the canonical position groups."""
    assert get_position_importance("OG") == get_position_importance("IOL")
    assert get_position_importance("DE") == get_position_importance("EDGE")


def test_position_importance_adjusts_board_score_and_validates_weight() -> None:
    """Position importance should influence, but not dominate, the base evaluation."""
    assert calculate_position_adjusted_ranking(80, "QB") > calculate_position_adjusted_ranking(80, "P")
    with pytest.raises(ValueError, match="between 0 and 1"):
        calculate_position_adjusted_ranking(80, "QB", 1.5)