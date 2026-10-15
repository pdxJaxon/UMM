"""Tests for structured, randomness-aware LLM prediction orchestration."""

import pytest

from app.services.llm_prediction import PredictionContext, predict_pick


class FakePredictionProvider:
    provider_name = "test-provider"
    model_name = "test-model"

    def __init__(self, payload):
        self.payload = payload
        self.randomness = None

    def complete(self, prompt: str, randomness: float):
        self.randomness = randomness
        assert "player-a" in prompt
        return self.payload


def _context() -> PredictionContext:
    return PredictionContext(
        team_id="team-8",
        team_name="Browns",
        draft_year=2027,
        pick_number=8,
        candidates=({"player_id": "player-a", "position": "QB"}, {"player_id": "player-b", "position": "OT"}),
        overall_randomness=25,
        team_randomness=85,
    )


def test_prediction_validates_candidate_and_preserves_provenance() -> None:
    provider = FakePredictionProvider(
        {
            "selected_player_id": "player-a",
            "confidence": 0.72,
            "alternatives": [{"player_id": "player-b", "score": 0.4}],
            "reasoning_factors": ["need fit"],
            "evidence": ["team_need:QB"],
        }
    )

    result = predict_pick(_context(), provider)

    assert result.selected_player_id == "player-a"
    assert result.model == "test-model"
    assert result.prompt_version == "umm-pick-v1"
    assert result.randomness == 60
    assert provider.randomness == 60


def test_prediction_rejects_player_outside_candidate_pool() -> None:
    provider = FakePredictionProvider({"selected_player_id": "player-x", "confidence": 0.9})

    with pytest.raises(ValueError, match="candidate pool"):
        predict_pick(_context(), provider)


def test_prediction_rejects_invalid_confidence() -> None:
    provider = FakePredictionProvider({"selected_player_id": "player-a", "confidence": 2})

    with pytest.raises(ValueError, match="confidence"):
        predict_pick(_context(), provider)