"""Generation and retrieval services for team-specific draft boards."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ExternalMockPickRecord,
    PlayerAthleticScoreRecord,
    PlayerDerogatoryConcernRecord,
    PlayerMeasurementRecord,
    PlayerRecord,
    TeamBoardEntryRecord,
    TeamBoardRecord,
    TeamDraftingTendencyRecord,
    TeamNeedRecord,
    TeamProspectMeetingRecord,
)
from app.services.draft_scoring import DraftScoreWeights, calculate_draft_score


def generate_team_board(
    session: Session,
    team_id: str,
    draft_year: int,
    candidates: Iterable[Mapping[str, Any]],
    scoring_weights: DraftScoreWeights | None = None,
    board_type: str = "default",
    user_id: str | None = None,
) -> TeamBoardRecord:
    """Generate and persist a new versioned board for one team."""
    weights = scoring_weights or DraftScoreWeights()
    previous_version = session.scalar(
        select(TeamBoardRecord.version)
        .where(
            TeamBoardRecord.team_id == team_id,
            TeamBoardRecord.draft_year == draft_year,
            TeamBoardRecord.board_type == board_type,
            TeamBoardRecord.user_id == user_id,
        )
        .order_by(TeamBoardRecord.version.desc())
        .limit(1)
    )
    board = TeamBoardRecord(
        team_id=team_id,
        user_id=user_id,
        draft_year=draft_year,
        board_type=board_type,
        version=(previous_version or 0) + 1,
        generated_at=datetime.now(UTC),
        scoring_version="draft-score-v1",
        scoring_weights=weights.__dict__,
    )
    session.add(board)
    session.flush()

    ranked = []
    for candidate in candidates:
        breakdown = calculate_draft_score(
            player=candidate,
            team_id=team_id,
            pick_number=int(candidate.get("pick_number", 1)),
            team_needs=candidate.get("team_needs", []),
            tendencies=candidate.get("tendencies", []),
            meetings=candidate.get("meetings", []),
            external_picks=candidate.get("external_picks", []),
            concerns=candidate.get("concerns", []),
            ranking_values=candidate.get("ranking_values", {}),
            weights=weights,
        )
        ranked.append((candidate, breakdown))

    ranked.sort(key=lambda item: item[1].final_score, reverse=True)
    for rank_position, (candidate, breakdown) in enumerate(ranked, start=1):
        session.add(
            TeamBoardEntryRecord(
                board_id=board.id,
                player_id=str(candidate["id"]),
                rank_position=rank_position,
                score=breakdown.final_score,
                score_breakdown=breakdown.as_dict(),
            )
        )
    session.commit()
    return board


def get_latest_team_board(session: Session, team_id: str, draft_year: int) -> TeamBoardRecord | None:
    """Return the latest default board for a team and draft year."""
    return get_latest_board(session, team_id, draft_year)


def get_latest_board(
    session: Session,
    team_id: str,
    draft_year: int,
    board_type: str = "default",
    user_id: str | None = None,
) -> TeamBoardRecord | None:
    """Return the latest board for a team, season, type, and optional owner."""
    return session.scalar(
        select(TeamBoardRecord)
        .where(
            TeamBoardRecord.team_id == team_id,
            TeamBoardRecord.draft_year == draft_year,
            TeamBoardRecord.board_type == board_type,
            TeamBoardRecord.user_id == user_id,
        )
        .order_by(TeamBoardRecord.version.desc())
        .limit(1)
    )


def copy_board_for_user(
    session: Session,
    source_board: TeamBoardRecord,
    user_id: str,
) -> TeamBoardRecord:
    """Create a user-owned editable copy of a default board."""
    board = TeamBoardRecord(
        team_id=source_board.team_id,
        user_id=user_id,
        draft_year=source_board.draft_year,
        board_type="personal",
        version=1,
        generated_at=datetime.now(UTC),
        scoring_version=source_board.scoring_version,
        scoring_weights=source_board.scoring_weights,
    )
    session.add(board)
    session.flush()
    for entry in sorted(source_board.entries, key=lambda item: item.rank_position):
        session.add(
            TeamBoardEntryRecord(
                board_id=board.id,
                player_id=entry.player_id,
                rank_position=entry.rank_position,
                score=entry.score,
                score_breakdown=entry.score_breakdown,
            )
        )
    session.commit()
    return board


def reorder_personal_board(
    session: Session,
    board: TeamBoardRecord,
    ordered_player_ids: list[str],
) -> TeamBoardRecord:
    """Persist a complete new player order for a user-owned board."""
    entries_by_player = {entry.player_id: entry for entry in board.entries if entry.is_active}
    if set(ordered_player_ids) != set(entries_by_player) or len(ordered_player_ids) != len(entries_by_player):
        raise ValueError("Board order must contain each active player exactly once")
    board.version += 1
    for rank_position, player_id in enumerate(ordered_player_ids, start=1):
        entries_by_player[player_id].rank_position = rank_position
    session.commit()
    return board


def generate_persisted_team_board(
    session: Session,
    team_id: str,
    draft_year: int,
    pick_number: int = 1,
) -> TeamBoardRecord:
    """Build a team board directly from persisted prospect and team signals."""
    players = session.scalars(
        select(PlayerRecord).where(
            PlayerRecord.draft_year == draft_year,
            PlayerRecord.eligibility_status == "eligible",
        )
    ).all()
    needs = _rows(session.scalars(select(TeamNeedRecord).where(TeamNeedRecord.team_id == team_id, TeamNeedRecord.draft_year == draft_year, TeamNeedRecord.is_active.is_(True))).all())
    tendencies = _rows(session.scalars(select(TeamDraftingTendencyRecord).where(TeamDraftingTendencyRecord.team_id == team_id, TeamDraftingTendencyRecord.is_active.is_(True))).all())
    external_picks = _rows(session.scalars(select(ExternalMockPickRecord).where(ExternalMockPickRecord.draft_year == draft_year, ExternalMockPickRecord.team_id == team_id)).all())
    candidates = []
    for player in players:
        measurements = session.scalars(
            select(PlayerMeasurementRecord).where(PlayerMeasurementRecord.player_id == player.id).order_by(PlayerMeasurementRecord.observed_at.desc()).limit(1)
        ).first()
        scores = session.scalars(select(PlayerAthleticScoreRecord).where(PlayerAthleticScoreRecord.player_id == player.id)).all()
        concerns = session.scalars(select(PlayerDerogatoryConcernRecord).where(PlayerDerogatoryConcernRecord.player_id == player.id)).all()
        meetings = session.scalars(select(TeamProspectMeetingRecord).where(TeamProspectMeetingRecord.team_id == team_id, TeamProspectMeetingRecord.player_id == player.id, TeamProspectMeetingRecord.draft_year == draft_year, TeamProspectMeetingRecord.is_active.is_(True))).all()
        candidates.append({
            "id": player.id,
            "position": player.position,
            "college_id": player.college_id,
            "ranking_values": _ranking_values(scores),
            "measurements": _measurement_values(measurements),
            "team_needs": needs,
            "tendencies": tendencies,
            "external_picks": external_picks,
            "concerns": concerns,
            "meetings": meetings,
            "pick_number": pick_number,
        })
    return generate_team_board(session, team_id, draft_year, candidates)


def _rows(records: list[object]) -> list[dict[str, object]]:
    """Convert SQLAlchemy records to dictionaries for scoring helpers."""
    return [{key: value for key, value in record.__dict__.items() if not key.startswith("_")} for record in records]


def _ranking_values(scores: list[PlayerAthleticScoreRecord]) -> dict[str, float]:
    """Map stored score metrics to the composite ranking signal names."""
    values: dict[str, float] = {}
    for score in scores:
        metric = score.metric_name.lower()
        if metric in {"pff", "pff_grade", "overall"} and score.score is not None:
            values["pff"] = float(score.score)
        elif metric in {"sparq", "ras"} and score.score is not None:
            values["sparq"] = float(score.score)
    return values


def _measurement_values(measurement: PlayerMeasurementRecord | None) -> dict[str, object]:
    """Map the latest measurement snapshot to scoring fields."""
    if measurement is None:
        return {}
    return {
        "height_inches": measurement.height_inches,
        "weight_lbs": measurement.weight_lbs,
        "hand_inches": measurement.hand_inches,
        "arm_inches": measurement.arm_inches,
    }