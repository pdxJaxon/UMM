"""Tests for external mock-draft consensus aggregation."""

from app.services.ranking_service import calculate_external_mock_consensus


def test_consensus_counts_player_frequency_for_team_pick() -> None:
    """The most frequently mocked player should rank first."""
    picks = [
        {"team_id": "team-1", "pick_number": 1, "player_id": "player-a"},
        {"team_id": "team-1", "pick_number": 1, "player_id": "player-a"},
        {"team_id": "team-1", "pick_number": 1, "player_id": "player-b"},
        {"team_id": "team-2", "pick_number": 1, "player_id": "player-c"},
    ]

    result = calculate_external_mock_consensus(picks, "team-1", 1)

    assert result[0]["player_id"] == "player-a"
    assert result[0]["mock_count"] == 2
    assert result[0]["consensus_percent"] == 66.67
    assert result[0]["influence_score"] == 6.67


def test_consensus_influence_is_capped_and_missing_context_is_empty() -> None:
    """Consensus remains minor and unrelated picks are excluded."""
    picks = [{"team_id": "team-1", "pick_number": 1, "player_id": "player-a"}]

    assert calculate_external_mock_consensus(picks, "team-1", 1, maximum_influence=5)[0]["influence_score"] == 5
    assert calculate_external_mock_consensus(picks, "team-1", 2) == []