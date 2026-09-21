"""Provider-neutral, structured LLM predictions for team draft picks."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class PredictionContext:
    """Evidence and controls supplied to the model for one team pick."""

    team_id: str
    team_name: str
    draft_year: int
    pick_number: int
    candidates: tuple[dict[str, Any], ...]
    team_needs: tuple[dict[str, Any], ...] = ()
    team_tendencies: tuple[dict[str, Any], ...] = ()
    overall_randomness: float = 50.0
    team_randomness: float = 50.0


@dataclass(frozen=True)
class PredictionResult:
    """Validated model decision with reproducibility metadata."""

    team_id: str
    pick_number: int
    selected_player_id: str
    confidence: float
    alternatives: tuple[dict[str, Any], ...]
    reasoning_factors: tuple[str, ...]
    evidence: tuple[str, ...]
    provider: str
    model: str
    prompt_version: str
    randomness: float


class PredictionProvider(Protocol):
    """Provider contract that can be benchmarked across frontier models."""

    provider_name: str
    model_name: str

    def complete(self, prompt: str, randomness: float) -> dict[str, Any]:
        """Return a decoded structured prediction payload."""


class OpenAICompatiblePredictionProvider:
    """Call an OpenAI-compatible chat-completions endpoint with JSON output."""

    provider_name = "openai-compatible"

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_url = api_url if api_url is not None else settings.llm_api_url
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model_name = model_name if model_name is not None else settings.llm_model
        self.timeout_seconds = timeout_seconds or settings.llm_request_timeout_seconds
        self.client = client or httpx.Client(timeout=self.timeout_seconds)

    def complete(self, prompt: str, randomness: float) -> dict[str, Any]:
        """Request one JSON prediction and reject malformed provider responses."""
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not configured")
        response = self.client.post(
            self.api_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model_name,
                "temperature": _temperature_from_randomness(randomness),
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "Return only the requested JSON object."},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("LLM response did not contain a valid JSON prediction") from exc
        if not isinstance(result, dict):
            raise ValueError("LLM prediction must be a JSON object")
        return result

    def close(self) -> None:
        """Close the internally owned HTTP client."""
        self.client.close()


def build_prediction_prompt(context: PredictionContext) -> str:
    """Build a stable, evidence-bounded prompt for one team selection."""
    payload = {
        "task": "Select the player this team is most likely to draft.",
        "constraints": [
            "Select exactly one player_id from candidates.",
            "Use only the supplied evidence.",
            "Treat randomness as calibrated unpredictability, not arbitrary noise.",
            "Return confidence from 0 to 1.",
        ],
        "draft": {
            "year": context.draft_year,
            "pick_number": context.pick_number,
            "team_id": context.team_id,
            "team_name": context.team_name,
        },
        "randomness": {
            "overall_percent": context.overall_randomness,
            "team_percent": context.team_randomness,
            "effective_percent": _effective_randomness(context.overall_randomness, context.team_randomness),
        },
        "team_needs": context.team_needs,
        "team_tendencies": context.team_tendencies,
        "candidates": context.candidates,
        "output_schema": {
            "selected_player_id": "string",
            "confidence": "number between 0 and 1",
            "alternatives": [{"player_id": "string", "score": "number between 0 and 1"}],
            "reasoning_factors": ["short string"],
            "evidence": ["source-backed evidence identifier"],
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def predict_pick(context: PredictionContext, provider: PredictionProvider) -> PredictionResult:
    """Generate and validate one model-driven team pick."""
    effective_randomness = _effective_randomness(context.overall_randomness, context.team_randomness)
    raw = provider.complete(build_prediction_prompt(context), effective_randomness)
    candidate_ids = {str(candidate.get("player_id")) for candidate in context.candidates}
    selected_player_id = str(raw.get("selected_player_id", ""))
    if selected_player_id not in candidate_ids:
        raise ValueError("LLM selected a player outside the available candidate pool")
    confidence = float(raw.get("confidence", -1))
    if not 0 <= confidence <= 1:
        raise ValueError("LLM confidence must be between 0 and 1")
    alternatives = tuple(raw.get("alternatives", ()))
    reasoning_factors = tuple(str(item) for item in raw.get("reasoning_factors", ()))
    evidence = tuple(str(item) for item in raw.get("evidence", ()))
    return PredictionResult(
        team_id=context.team_id,
        pick_number=context.pick_number,
        selected_player_id=selected_player_id,
        confidence=confidence,
        alternatives=alternatives,
        reasoning_factors=reasoning_factors,
        evidence=evidence,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_version=settings.llm_prompt_version,
        randomness=effective_randomness,
    )


def _effective_randomness(overall_randomness: float, team_randomness: float) -> float:
    """Apply the same baseline-plus-team calibration used by draft simulation."""
    return min(max(float(overall_randomness) + float(team_randomness) - 50.0, 0.0), 100.0)


def _temperature_from_randomness(randomness: float) -> float:
    """Map product randomness to a conservative model temperature range."""
    return round(min(max(float(randomness), 0.0), 100.0) / 100.0, 2)