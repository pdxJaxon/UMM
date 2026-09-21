"""Historical evaluation helpers for UMockMe board predictions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import PredictionEvaluationRecord


def evaluate_prediction_accuracy(
    predictions: Iterable[Mapping[str, object]],
    actual_picks: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Compare one ranked board with actual selections for the same team.

    ``predictions`` and ``actual_picks`` must contain ``pick_number`` and
    ``player_id``. A player hit means the board included the selected player
    somewhere in the evaluated picks; exact accuracy additionally requires the
    predicted and actual pick numbers to match.
    """
    predicted_by_player = {
        str(prediction["player_id"]): int(prediction["pick_number"])
        for prediction in predictions
        if prediction.get("player_id") is not None and prediction.get("pick_number") is not None
    }
    actual = [
        (int(pick["pick_number"]), str(pick["player_id"]))
        for pick in actual_picks
        if pick.get("player_id") is not None and pick.get("pick_number") is not None
    ]
    exact_hits = sum(
        1
        for pick_number, player_id in actual
        if predicted_by_player.get(player_id) == pick_number
    )
    player_hits = sum(1 for _, player_id in actual if player_id in predicted_by_player)
    pick_errors = [
        abs(predicted_by_player[player_id] - pick_number)
        for pick_number, player_id in actual
        if player_id in predicted_by_player
    ]
    evaluated_picks = len(actual)

    return {
        "evaluated_picks": evaluated_picks,
        "exact_hits": exact_hits,
        "player_hits": player_hits,
        "exact_pick_rate": round(exact_hits / evaluated_picks * 100, 2) if evaluated_picks else 0.0,
        "player_hit_rate": round(player_hits / evaluated_picks * 100, 2) if evaluated_picks else 0.0,
        "mean_absolute_pick_error": round(sum(pick_errors) / len(pick_errors), 2) if pick_errors else None,
    }


def record_prediction_evaluation(
    session: Session,
    *,
    team_id: str,
    draft_year: int,
    predictions: Iterable[Mapping[str, object]],
    actual_picks: Iterable[Mapping[str, object]],
    scoring_version: str,
    source_name: str,
    board_id: int | None = None,
    evaluation_scope: str = "first_round",
    evaluated_at: datetime | None = None,
) -> PredictionEvaluationRecord:
    """Evaluate a board and stage its immutable scorecard for persistence."""
    metrics = evaluate_prediction_accuracy(predictions, actual_picks)
    record = PredictionEvaluationRecord(
        team_id=team_id,
        board_id=board_id,
        draft_year=draft_year,
        evaluation_scope=evaluation_scope,
        scoring_version=scoring_version,
        evaluated_picks=metrics["evaluated_picks"],
        exact_hits=metrics["exact_hits"],
        player_hits=metrics["player_hits"],
        exact_pick_rate=metrics["exact_pick_rate"],
        player_hit_rate=metrics["player_hit_rate"],
        mean_absolute_pick_error=metrics["mean_absolute_pick_error"],
        evaluated_at=evaluated_at or datetime.now(UTC),
        source_name=source_name,
    )
    session.add(record)
    return record