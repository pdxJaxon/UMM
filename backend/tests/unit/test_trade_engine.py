"""Tests for historical-tendency-driven draft trade evaluation."""

from app.services.trade_engine import evaluate_trade, pick_value


def test_pick_value_decreases_for_later_selections() -> None:
    """The value chart should price an earlier selection above a later one."""
    assert pick_value(1) == 1000
    assert pick_value(2) < pick_value(1)


def test_trade_requires_both_teams_historic_willingness() -> None:
    """A single team's trade history must not force a unilateral swap."""
    tendencies = {
        "team-1": [{"tendency_type": "trade_down", "preference_score": 100, "confidence_score": 100}],
        "team-2": [],
    }
    assert evaluate_trade(["team-1", "team-2"], 0, tendencies) is None


def test_trade_selects_earliest_willing_partner_and_records_evidence() -> None:
    """The engine should prefer the earliest willing partner and explain why."""
    tendencies = {
        "team-1": [{"tendency_type": "trade_down", "preference_score": 80, "confidence_score": 100, "sample_size": 3}],
        "team-2": [{"tendency_type": "trade_up", "preference_score": 80, "confidence_score": 100, "sample_size": 2}],
        "team-3": [{"tendency_type": "trade_up", "preference_score": 90, "confidence_score": 100, "sample_size": 6}],
    }

    proposal = evaluate_trade(["team-1", "team-2", "team-3"], 0, tendencies)

    assert proposal is not None
    assert proposal.moving_up_team_id == "team-2"
    assert proposal.acquired_pick_number == 2
    assert proposal.evidence["moving_down"]["sample_size"] == 3
    assert proposal.value_delta > 0