"""Tests for explainable team-specific draft scoring."""

from app.services.draft_scoring import DraftScoreWeights, calculate_draft_score


def test_draft_score_returns_component_breakdown() -> None:
    """The final score should expose each contributing signal."""
    breakdown = calculate_draft_score(
        player={"id": "player-a", "position": "QB", "college_id": "alabama", "conference": "SEC"},
        team_id="team-1",
        pick_number=1,
        team_needs=[{"position_code": "QB", "need_score": 100}],
        tendencies=[{"tendency_type": "school", "target_value": "alabama", "preference_score": 90, "confidence_score": 100}],
        meetings=[{"meeting_type": "formal"}],
        external_picks=[{"team_id": "team-1", "pick_number": 1, "player_id": "player-a"}],
        concerns=[],
        ranking_values={"pff": 90, "nfl": 88, "sparq": 85},
    )

    result = breakdown.as_dict()
    assert result["team_need"] == 100
    assert result["team_tendency"] == 90
    assert result["external_consensus"] == 10
    assert 0 <= result["final_score"] <= 100


def test_unavailable_player_loses_availability_component() -> None:
    """Unavailable candidates should receive no availability bonus."""
    breakdown = calculate_draft_score(
        player={"id": "player-a", "position": "P", "is_available": False},
        team_id="team-1",
        pick_number=1,
        team_needs=[], tendencies=[], meetings=[], external_picks=[], concerns=[], ranking_values={"pff": 50},
    )

    assert breakdown.availability_bonus == 0


def test_source_fallback_applies_concern_penalty_to_single_pass_iterables() -> None:
    breakdown = calculate_draft_score(
        player={"id": "projected", "position": "WR", "source_evaluation": 100},
        team_id="team-1", pick_number=1,
        team_needs=[], tendencies=[], meetings=[], external_picks=[],
        concerns=iter([{"severity": "severe", "confidence": "verified", "status": "open"}]),
        ranking_values={},
    )

    assert breakdown.player_evaluation == 70


def test_college_strength_is_an_explainable_five_percent_score_factor() -> None:
    """Known schools use the issue scores; unknown schools receive a neutral score."""
    alabama = calculate_draft_score(
        player={"id": "a", "position": "QB", "college_id": "alabama"},
        team_id="team-1", pick_number=1,
        team_needs=[], tendencies=[], meetings=[], external_picks=[], concerns=[],
        ranking_values={"pff": 80},
    )
    uab = calculate_draft_score(
        player={"id": "b", "position": "QB", "college_id": "uab"},
        team_id="team-1", pick_number=1,
        team_needs=[], tendencies=[], meetings=[], external_picks=[], concerns=[],
        ranking_values={"pff": 80},
    )
    unknown = calculate_draft_score(
        player={"id": "c", "position": "QB", "college_id": "unknown-school"},
        team_id="team-1", pick_number=1,
        team_needs=[], tendencies=[], meetings=[], external_picks=[], concerns=[],
        ranking_values={"pff": 80},
    )

    assert alabama.school_strength == 100
    assert uab.school_strength == 40
    assert unknown.school_strength == 50
    assert alabama.final_score - uab.final_score == 3
    assert DraftScoreWeights().player_evaluation == 0.40
    assert DraftScoreWeights().school_strength == 0.05