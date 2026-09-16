"""Tests for team drafting tendency matching and weighting."""

from app.services.ranking_service import calculate_team_tendency_fit


def test_school_and_conference_tendencies_match_player_context() -> None:
    """School and conference preferences should contribute to player fit."""
    tendencies = [
        {"tendency_type": "school", "target_value": "alabama", "preference_score": 90, "confidence_score": 100},
        {"tendency_type": "conference", "target_value": "SEC", "preference_score": 80, "confidence_score": 50},
    ]
    player = {"position": "WR", "college_id": "alabama", "conference": "SEC"}

    assert calculate_team_tendency_fit(tendencies, player) == 86.66666666666667


def test_measurement_tendency_is_position_specific() -> None:
    """A tall-WR rule should match height but not affect quarterbacks."""
    tendency = [{
        "tendency_type": "measurement",
        "position_code": "WR",
        "metric_name": "height_inches",
        "minimum_value": 76,
        "preference_score": 90,
        "confidence_score": 100,
    }]

    assert calculate_team_tendency_fit(tendency, {"position": "WR", "measurements": {"height_inches": 77}}) == 90
    assert calculate_team_tendency_fit(tendency, {"position": "QB", "measurements": {"height_inches": 77}}) == 0


def test_off_field_tendency_is_explicit_and_inactive_rules_are_ignored() -> None:
    """Character-risk preferences should be explicit and inactive rules ignored."""
    tendencies = [
        {"tendency_type": "off_field", "target_value": "low_risk", "preference_score": 95, "confidence_score": 100},
        {"tendency_type": "school", "target_value": "alabama", "preference_score": 100, "confidence_score": 100, "is_active": False},
    ]

    assert calculate_team_tendency_fit(tendencies, {"character_profile": "low_risk"}) == 95