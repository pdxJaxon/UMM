"""Tests for weighted team-prospect meeting scoring."""

from app.services.ranking_service import calculate_meeting_fit_score


def test_meeting_weights_follow_business_priority() -> None:
    """Dinner and facility visits should outweigh informal meetings."""
    informal = calculate_meeting_fit_score([{"meeting_type": "informal"}])
    formal = calculate_meeting_fit_score([{"meeting_type": "formal"}])
    dinner = calculate_meeting_fit_score([{"meeting_type": "dinner"}])
    facility = calculate_meeting_fit_score([{"meeting_type": "facility_invite"}])

    assert informal < formal < dinner
    assert facility == dinner


def test_repeated_meetings_use_diminishing_returns() -> None:
    """Multiple contacts should matter without exceeding the score cap."""
    score = calculate_meeting_fit_score([
        {"meeting_type": "dinner"},
        {"meeting_type": "formal"},
        {"meeting_type": "pro_day"},
    ])

    assert score == 100.0


def test_inactive_meetings_are_ignored() -> None:
    """Invalidated meeting records must not influence draft logic."""
    assert calculate_meeting_fit_score([{"meeting_type": "dinner", "is_active": False}]) == 0.0