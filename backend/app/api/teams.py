"""Public reference-data endpoints for NFL teams."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_optional_current_user
from app.db.models import (
    CollegeRecord,
    PlayerRecord,
    TeamBoardRecord,
    TeamDraftingTendencyRecord,
    TeamNeedRecord,
    TeamProspectMeetingRecord,
    TeamRecord,
    UserRecord,
)
from app.db.session import get_db
from app.services.team_board_service import copy_board_for_user, generate_persisted_team_board, get_latest_board, get_latest_team_board, reorder_personal_board

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("")
def list_teams(session: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Return NFL teams ordered by their configured draft-order value."""
    teams = session.scalars(select(TeamRecord).order_by(TeamRecord.draft_order)).all()
    return [
        {
            "id": team.id,
            "name": team.name,
            "city": team.city,
            "abbreviation": team.abbreviation,
            "draft_order": team.draft_order,
            "randomness_score": float(team.randomness_score),
            "logo_url": team.logo_url,
            "helmet_url": team.helmet_url,
            "official_url": team.official_url,
        }
        for team in teams
    ]


@router.get("/{team_id}/needs")
def list_team_needs(
    team_id: str,
    draft_year: int,
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Return active, season-specific needs for one NFL team."""
    needs = session.scalars(
        select(TeamNeedRecord)
        .where(
            TeamNeedRecord.team_id == team_id,
            TeamNeedRecord.draft_year == draft_year,
            TeamNeedRecord.is_active.is_(True),
        )
        .order_by(TeamNeedRecord.need_score.desc(), TeamNeedRecord.position_code)
    ).all()
    return [
        {
            "id": need.id,
            "team_id": need.team_id,
            "draft_year": need.draft_year,
            "position_code": need.position_code,
            "role_level": need.role_level,
            "need_score": float(need.need_score),
            "quantity": need.quantity,
            "source_name": need.source_name,
            "source_url": need.source_url,
            "rationale": need.rationale,
            "observed_at": need.observed_at.isoformat(),
        }
        for need in needs
    ]


@router.get("/{team_id}/tendencies")
def list_team_tendencies(
    team_id: str,
    draft_year: int | None = None,
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Return active team drafting tendencies, optionally scoped to a season."""
    query = select(TeamDraftingTendencyRecord).where(
        TeamDraftingTendencyRecord.team_id == team_id,
        TeamDraftingTendencyRecord.is_active.is_(True),
    )
    if draft_year is not None:
        query = query.where(
            (TeamDraftingTendencyRecord.draft_year == draft_year)
            | (TeamDraftingTendencyRecord.draft_year.is_(None))
        )
    tendencies = session.scalars(query.order_by(TeamDraftingTendencyRecord.preference_score.desc())).all()
    return [
        {
            "id": tendency.id,
            "team_id": tendency.team_id,
            "draft_year": tendency.draft_year,
            "actor_type": tendency.actor_type,
            "actor_id": tendency.actor_id,
            "actor_name": tendency.actor_name,
            "tendency_type": tendency.tendency_type,
            "position_code": tendency.position_code,
            "metric_name": tendency.metric_name,
            "target_value": tendency.target_value,
            "minimum_value": float(tendency.minimum_value) if tendency.minimum_value is not None else None,
            "maximum_value": float(tendency.maximum_value) if tendency.maximum_value is not None else None,
            "preference_score": float(tendency.preference_score),
            "confidence_score": float(tendency.confidence_score),
            "sample_size": tendency.sample_size,
            "source_name": tendency.source_name,
            "source_url": tendency.source_url,
            "rationale": tendency.rationale,
            "observed_at": tendency.observed_at.isoformat(),
        }
        for tendency in tendencies
    ]


@router.get("/{team_id}/meetings")
def list_team_meetings(
    team_id: str,
    draft_year: int,
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Return active prospect meetings for a team and draft year."""
    meetings = session.scalars(
        select(TeamProspectMeetingRecord)
        .where(
            TeamProspectMeetingRecord.team_id == team_id,
            TeamProspectMeetingRecord.draft_year == draft_year,
            TeamProspectMeetingRecord.is_active.is_(True),
        )
        .order_by(TeamProspectMeetingRecord.importance_score.desc())
    ).all()
    return [
        {
            "id": meeting.id,
            "team_id": meeting.team_id,
            "player_id": meeting.player_id,
            "draft_year": meeting.draft_year,
            "meeting_type": meeting.meeting_type,
            "importance_score": float(meeting.importance_score),
            "occurred_at": meeting.occurred_at.isoformat() if meeting.occurred_at else None,
            "source_name": meeting.source_name,
            "source_url": meeting.source_url,
            "notes": meeting.notes,
        }
        for meeting in meetings
    ]


@router.get("/{team_id}/board")
def get_team_board(
    team_id: str,
    draft_year: int,
    board_type: str = Query(default="default", pattern="^(default|personal)$"),
    current_user: UserRecord | None = Depends(get_optional_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Return the latest generated default or personal board for a team and season."""
    if board_type == "personal" and current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    board = get_latest_board(
        session,
        team_id,
        draft_year,
        board_type=board_type,
        user_id=current_user.id if board_type == "personal" and current_user else None,
    )
    if board is None:
        return {"team_id": team_id, "draft_year": draft_year, "board": None, "entries": []}
    entry_rows = []
    for entry in sorted(board.entries, key=lambda item: item.rank_position):
        if not entry.is_active:
            continue
        player = session.get(PlayerRecord, entry.player_id)
        college = session.get(CollegeRecord, player.college_id) if player else None
        entry_rows.append(
            {
                "player_id": entry.player_id,
                "rank_position": entry.rank_position,
                "score": float(entry.score),
                "score_breakdown": entry.score_breakdown,
                "first_name": player.first_name if player else None,
                "last_name": player.last_name if player else None,
                "position": player.position if player else None,
                "college_id": player.college_id if player else None,
                "college_name": college.name if college else None,
                "college_abbreviation": college.abbreviation if college else None,
            }
        )

    return {
        "team_id": board.team_id,
        "draft_year": board.draft_year,
        "board": {
            "id": board.id,
            "version": board.version,
            "board_type": board.board_type,
            "generated_at": board.generated_at.isoformat(),
            "scoring_version": board.scoring_version,
            "scoring_weights": board.scoring_weights,
        },
        "entries": entry_rows,
    }


@router.post("/{team_id}/board/generate")
def generate_team_board_endpoint(
    team_id: str,
    draft_year: int,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Generate a fresh default board from current persisted signal data."""
    del current_user
    board = generate_persisted_team_board(session, team_id, draft_year)
    return {
        "team_id": board.team_id,
        "draft_year": board.draft_year,
        "board_id": board.id,
        "version": board.version,
        "status": "generated",
    }


class BoardOrderRequest(BaseModel):
    """Payload containing the complete desired player order."""

    player_ids: list[str]


@router.post("/{team_id}/board/copy")
def copy_team_board_endpoint(
    team_id: str,
    draft_year: int,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Copy the latest default board into the authenticated user's workspace."""
    source_board = get_latest_team_board(session, team_id, draft_year)
    if source_board is None:
        raise HTTPException(status_code=404, detail="Default team board has not been generated")
    board = copy_board_for_user(session, source_board, current_user.id)
    return {"board_id": board.id, "team_id": board.team_id, "draft_year": board.draft_year, "version": board.version}


@router.put("/{team_id}/board/{board_id}/order")
def reorder_team_board_endpoint(
    team_id: str,
    board_id: int,
    payload: BoardOrderRequest,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Save a reordered player list on an owned personal board."""
    board = session.get(TeamBoardRecord, board_id)
    if board is None or board.team_id != team_id or board.user_id != current_user.id or board.board_type != "personal":
        raise HTTPException(status_code=404, detail="Personal board not found")
    try:
        board = reorder_personal_board(session, board, payload.player_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"board_id": board.id, "version": board.version, "player_ids": payload.player_ids}