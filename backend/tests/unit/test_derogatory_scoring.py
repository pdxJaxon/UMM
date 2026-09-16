"""Tests for transparent derogatory-concern ranking adjustments."""

from app.services.ranking_service import (
    calculate_adjusted_umm_ranking,
    calculate_derogatory_penalty,
)


def test_verified_severe_issue_has_more_weight_than_poor_grades() -> None:
    """Severity and confidence should distinguish major conduct issues from minor concerns."""
    poor_grades = [{"severity": "minor", "confidence": "verified", "status": "open"}]
    domestic_abuse_charge = [{"severity": "severe", "confidence": "reported", "status": "open"}]

    assert calculate_derogatory_penalty(domestic_abuse_charge) > calculate_derogatory_penalty(poor_grades)


def test_dismissed_or_unknown_concern_does_not_reduce_ranking() -> None:
    """Dismissed and unclassified records should not create an automatic penalty."""
    concerns = [
        {"severity": "severe", "confidence": "verified", "status": "dismissed"},
        {"severity": "unknown", "confidence": "unknown", "status": "open"},
    ]

    assert calculate_derogatory_penalty(concerns) == 0


def test_penalty_is_capped_and_adjusted_score_cannot_be_negative() -> None:
    """Many serious records cannot drive the adjusted ranking below zero."""
    concerns = [{"severity": "severe", "confidence": "verified", "status": "open"}] * 5
    values = {"pff": 90, "nfl": 90, "sparq": 90, "school_affinity": 90, "team_connection": 90}

    assert calculate_derogatory_penalty(concerns) == 30
    assert calculate_adjusted_umm_ranking(values, concerns) == 60