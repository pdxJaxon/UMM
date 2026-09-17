"""Explainable composite scoring for team-specific draft decisions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, asdict
from typing import Any

from app.services.ranking_service import (
    calculate_adjusted_umm_ranking,
    calculate_external_mock_consensus,
    calculate_meeting_fit_score,
    calculate_position_adjusted_ranking,
    calculate_team_need_score,
    calculate_team_tendency_fit,
)


@dataclass(frozen=True)
class DraftScoreWeights:
    """Weights for the team-specific draft score components."""

    player_evaluation: float = 0.45
    team_need: float = 0.20
    position_importance: float = 0.10
    team_tendency: float = 0.10
    meeting_fit: float = 0.05
    external_consensus: float = 0.05
    availability_bonus: float = 0.05


@dataclass(frozen=True)
class DraftScoreBreakdown:
    """Auditable component values and final score for one candidate."""

    player_evaluation: float
    team_need: float
    position_importance: float
    team_tendency: float
    meeting_fit: float
    external_consensus: float
    availability_bonus: float
    final_score: float

    def as_dict(self) -> dict[str, float]:
        """Return the breakdown as a JSON-ready dictionary."""
        return asdict(self)


def calculate_draft_score(
    player: Mapping[str, Any],
    team_id: str,
    pick_number: int,
    team_needs: Iterable[Mapping[str, object]],
    tendencies: Iterable[Mapping[str, object]],
    meetings: Iterable[Mapping[str, object]],
    external_picks: Iterable[Mapping[str, object]],
    concerns: Iterable[Mapping[str, object]],
    ranking_values: dict[str, float],
    weights: DraftScoreWeights | None = None,
) -> DraftScoreBreakdown:
    """Calculate a bounded, explainable score for a team/player pairing."""
    weights = weights or DraftScoreWeights()
    player_evaluation = calculate_adjusted_umm_ranking(ranking_values, concerns)
    position = str(player.get("position", ""))
    position_adjusted = calculate_position_adjusted_ranking(player_evaluation, position)
    need = calculate_team_need_score(team_needs, position)
    tendency = calculate_team_tendency_fit(tendencies, player)
    meeting = calculate_meeting_fit_score(meetings)
    consensus_rows = calculate_external_mock_consensus(external_picks, team_id, pick_number)
    consensus = next(
        (float(row["influence_score"]) for row in consensus_rows if row["player_id"] == str(player.get("id"))),
        0.0,
    )
    availability = 100.0 if player.get("is_available", True) else 0.0
    components = {
        "player_evaluation": player_evaluation,
        "team_need": need,
        "position_importance": position_adjusted,
        "team_tendency": tendency,
        "meeting_fit": meeting,
        "external_consensus": consensus,
        "availability_bonus": availability,
    }
    final_score = sum(components[name] * getattr(weights, name) for name in components)
    return DraftScoreBreakdown(**components, final_score=min(max(final_score, 0.0), 100.0))