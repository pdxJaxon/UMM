"""Tests for historical prediction evaluation metrics."""

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.services.prediction_accuracy import evaluate_prediction_accuracy
from app.services.prediction_accuracy import record_prediction_evaluation


def test_evaluation_reports_exact_hits_player_hits_and_pick_error() -> None:
    predictions = [
        {"pick_number": 1, "player_id": "player-a"},
        {"pick_number": 2, "player_id": "player-c"},
        {"pick_number": 3, "player_id": "player-b"},
    ]
    actual_picks = [
        {"pick_number": 1, "player_id": "player-a"},
        {"pick_number": 2, "player_id": "player-b"},
        {"pick_number": 3, "player_id": "player-x"},
    ]

    result = evaluate_prediction_accuracy(predictions, actual_picks)

    assert result == {
        "evaluated_picks": 3,
        "predicted_picks": 3,
        "exact_hits": 1,
        "player_hits": 2,
        "wrong_player_picks": 2,
        "missing_predictions": 0,
        "exact_pick_rate": 33.33,
        "player_hit_rate": 66.67,
        "selection_error_rate": 66.67,
        "mean_absolute_pick_error": 0.5,
    }


def test_empty_evaluation_has_zero_rates_and_no_error() -> None:
    result = evaluate_prediction_accuracy([], [])

    assert result["evaluated_picks"] == 0
    assert result["predicted_picks"] == 0
    assert result["exact_pick_rate"] == 0.0
    assert result["player_hit_rate"] == 0.0
    assert result["selection_error_rate"] == 0.0
    assert result["mean_absolute_pick_error"] is None


def test_wrong_board_reports_selection_errors_instead_of_zero_error() -> None:
    result = evaluate_prediction_accuracy(
        [{"pick_number": 1, "player_id": "wrong"}],
        [{"pick_number": 1, "player_id": "actual"}],
    )

    assert result["wrong_player_picks"] == 1
    assert result["missing_predictions"] == 0
    assert result["selection_error_rate"] == 100.0


def test_record_evaluation_persists_scorecard_metadata() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    evaluated_at = datetime(2026, 6, 1, tzinfo=UTC)

    with Session(engine) as session:
        record = record_prediction_evaluation(
            session,
            team_id="team-1",
            draft_year=2026,
            predictions=[{"pick_number": 1, "player_id": "player-a"}],
            actual_picks=[{"pick_number": 1, "player_id": "player-a"}],
            scoring_version="umm-v1",
            source_name="nflverse",
            evaluated_at=evaluated_at,
        )
        session.commit()

        persisted = session.get(type(record), record.id)
        assert persisted is not None
        assert persisted.exact_pick_rate == 100
        assert persisted.source_name == "nflverse"