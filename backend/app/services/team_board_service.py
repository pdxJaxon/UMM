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
from app.services.draft_order import latest_league_refresh
from app.services.prospect_pool import latest_projected_snapshot, pool_filter, snapshot_rankings

DRAFT_SCORING_VERSION = "draft-score-v3-school-position"


def generate_team_board(
    session: Session,
    team_id: str,
    draft_year: int,
    candidates: Iterable[Mapping[str, Any]],
    scoring_weights: DraftScoreWeights | None = None,
    board_type: str = "default",
    user_id: str | None = None,
    *,
    commit: bool = True,
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
        scoring_version=DRAFT_SCORING_VERSION,
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
                score_breakdown={**breakdown.as_dict(), **candidate.get("source_provenance", {})},
            )
        )
    if commit:
        session.commit()
    else:
        session.flush()
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
    if source_board.board_type != "default" or source_board.user_id is not None:
        raise ValueError("Only a default team board can be copied")
    active_entries = sorted(
        (entry for entry in source_board.entries if entry.is_active),
        key=lambda entry: entry.rank_position,
    )
    if not active_entries:
        raise ValueError("The default board has no active prospects; generate it before copying")
    previous = get_latest_board(
        session, source_board.team_id, source_board.draft_year, board_type="personal", user_id=user_id,
    )
    board = TeamBoardRecord(
        team_id=source_board.team_id,
        user_id=user_id,
        draft_year=source_board.draft_year,
        board_type="personal",
        version=previous.version + 1 if previous is not None else 1,
        generated_at=datetime.now(UTC),
        scoring_version=source_board.scoring_version,
        scoring_weights=source_board.scoring_weights,
    )
    session.add(board)
    session.flush()
    for rank_position, entry in enumerate(active_entries, start=1):
        session.add(
            TeamBoardEntryRecord(
                board_id=board.id,
                player_id=entry.player_id,
                rank_position=rank_position,
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
    pick_number: int | None = None,
    *,
    commit: bool = True,
) -> TeamBoardRecord:
    """Build a team board directly from persisted prospect and team signals."""
    if pick_number is None:
        refresh = latest_league_refresh(session, draft_year)
        pick_number = refresh.manifest["draft_order"].index(team_id) + 1 if refresh is not None else 1
    snapshot = latest_projected_snapshot(session, draft_year)
    snapshot_id = snapshot.id if snapshot is not None else None
    rankings = snapshot_rankings(session, snapshot_id)
    players = session.scalars(
        select(PlayerRecord).where(
            pool_filter(draft_year, snapshot_id),
        )
    ).all()
    needs = _rows(session.scalars(select(TeamNeedRecord).where(TeamNeedRecord.team_id == team_id, TeamNeedRecord.draft_year == draft_year, TeamNeedRecord.is_active.is_(True))).all())
    tendencies = _rows(session.scalars(select(TeamDraftingTendencyRecord).where(TeamDraftingTendencyRecord.team_id == team_id, TeamDraftingTendencyRecord.is_active.is_(True))).all())
    external_picks = _rows(session.scalars(select(ExternalMockPickRecord).where(ExternalMockPickRecord.draft_year == draft_year, ExternalMockPickRecord.team_id == team_id)).all())
    candidates = []
    for player in players:
        ranking = rankings.get(player.id)
        source_evaluation = (
            100.0 * (snapshot.prospect_count - ranking.overall_rank + 1) / snapshot.prospect_count
            if snapshot is not None and ranking is not None else None
        )
        measurements = session.scalars(
            select(PlayerMeasurementRecord).where(PlayerMeasurementRecord.player_id == player.id).order_by(PlayerMeasurementRecord.observed_at.desc()).limit(1)
        ).first()
        scores = session.scalars(select(PlayerAthleticScoreRecord).where(PlayerAthleticScoreRecord.player_id == player.id)).all()
        ranking_values = _ranking_values(scores)
        concerns = session.scalars(select(PlayerDerogatoryConcernRecord).where(PlayerDerogatoryConcernRecord.player_id == player.id)).all()
        meetings = session.scalars(select(TeamProspectMeetingRecord).where(TeamProspectMeetingRecord.team_id == team_id, TeamProspectMeetingRecord.player_id == player.id, TeamProspectMeetingRecord.draft_year == draft_year, TeamProspectMeetingRecord.is_active.is_(True))).all()
        candidates.append({
            "id": player.id,
            "position": player.position,
            "college_id": player.college_id,
            "ranking_values": ranking_values,
            "source_evaluation": source_evaluation,
            "source_provenance": {
                "source_rank": ranking.overall_rank,
                "source_snapshot_id": snapshot.id,
                "source_name": snapshot.source_name,
                "source_evaluation": source_evaluation,
                "evaluation_basis": "stored_signals" if ranking_values else "source_rank_percentile",
            } if ranking is not None and snapshot is not None else {},
            "measurements": _measurement_values(measurements),
            "team_needs": needs,
            "tendencies": tendencies,
            "external_picks": external_picks,
            "concerns": concerns,
            "meetings": meetings,
            "pick_number": pick_number,
        })
    return generate_team_board(session, team_id, draft_year, candidates, commit=commit)


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