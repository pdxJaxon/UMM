"""Tests for position importance and ranking integration."""

import pytest

from app.services.ranking_service import (
    MAX_REACH_BY_ROUND,
    calculate_position_adjusted_ranking,
    candidates_within_team_need_reach,
    get_position_importance,
)


def test_quarterback_is_more_important_than_punter() -> None:
    """The baseline should reflect the requested premium-position ordering."""
    assert get_position_importance("QB") > get_position_importance("P")
    assert get_position_importance("P") == get_position_importance("LS")


def test_position_aliases_map_to_position_groups() -> None:
    """Legacy scouting labels should map to the canonical position groups."""
    assert get_position_importance("OG") == get_position_importance("IOL")
    assert get_position_importance("DE") == get_position_importance("EDGE")
    assert get_position_importance("ED") == 90
    assert get_position_importance("HB") == 70
    assert get_position_importance("T") == 90
    assert get_position_importance("C") == get_position_importance("G") == 70
    assert get_position_importance("NT") == 60
    assert get_position_importance("DL") == 70
    assert get_position_importance("LS") == 30


def test_position_importance_adjusts_board_score_and_validates_weight() -> None:
    """Position importance should influence, but not dominate, the base evaluation."""
    assert calculate_position_adjusted_ranking(80, "QB") > calculate_position_adjusted_ranking(80, "P")
    with pytest.raises(ValueError, match="between 0 and 1"):
        calculate_position_adjusted_ranking(80, "QB", 1.5)


@pytest.mark.parametrize(
    ("round_number", "reach_limit"),
    [(1, 12), (2, 15), (3, 20), (4, 25), (5, 35), (6, 60), (7, 150)],
)
def test_reach_limit_prioritizes_first_high_need_within_round_cap(round_number, reach_limit) -> None:
    candidates = ["best", "need-near", "need-at-limit", "need-beyond-limit"]
    ranks = {
        "best": 10,
        "need-near": 14,
        "need-at-limit": 10 + reach_limit,
        "need-beyond-limit": 11 + reach_limit,
    }

    assert candidates_within_team_need_reach(
        candidates,
        {
            "best": "QB",
            "need-near": "RB",
            "need-at-limit": "WR",
            "need-beyond-limit": "WR",
        },
        ranks,
        [
            {"position_code": "WR", "need_score": 70},
            {"position_code": "RB", "need_score": 75},
        ],
        round_number,
    ) == ["need-near", "best", "need-at-limit"]


def test_reach_limit_falls_back_to_best_available_without_a_reachable_high_need() -> None:
    candidates = ["best", "low-need", "out-of-range"]

    assert candidates_within_team_need_reach(
        candidates,
        {"best": "QB", "low-need": "WR", "out-of-range": "RB"},
        {"best": 10, "low-need": 11, "out-of-range": 23},
        [
            {"position_code": "WR", "need_score": 69},
            {"position_code": "RB", "need_score": 90},
        ],
        1,
    ) == ["best"]


def test_reach_limit_matches_position_aliases_and_validates_inputs() -> None:
    assert candidates_within_team_need_reach(
        ["best", "need"],
        {"best": "QB", "need": "ED"},
        {"best": 1, "need": 2},
        [{"position_code": "EDGE", "need_score": 80}],
        1,
    ) == ["need", "best"]
    assert MAX_REACH_BY_ROUND[7] == 150
    with pytest.raises(ValueError, match="between 1 and 7"):
        candidates_within_team_need_reach(["best"], {}, {}, [], 8)