"""Tests for configurable team and per-pick draft randomness."""

import random

import pytest

from app.services.ranking_service import select_with_team_randomness
from app.services.draft_repository import DraftRepository


def test_zero_randomness_is_deterministic() -> None:
    """Predictable teams should always choose the top candidate."""
    assert select_with_team_randomness(["a", "b", "c"], 0, random.Random(7)) == ("a", 0.0)


def test_full_randomness_can_select_any_candidate() -> None:
    """Unpredictable teams should have the full candidate window available."""
    selected, applied = select_with_team_randomness(["a", "b", "c"], 100, random.Random(2))
    assert selected in {"a", "b", "c"}
    assert applied == 100.0


def test_randomness_validates_empty_candidates() -> None:
    """Selection cannot proceed without available players."""
    with pytest.raises(ValueError, match="candidate"):
        select_with_team_randomness([], 50)


def test_overall_randomness_shifts_team_profile() -> None:
    """The overall setting moves a team profile while preserving its difference."""
    assert DraftRepository._effective_randomness(50, 85) == 85
    assert DraftRepository._effective_randomness(25, 85) == 60
    assert DraftRepository._effective_randomness(80, 20) == 50