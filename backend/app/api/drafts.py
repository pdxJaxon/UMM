"""REST endpoints for creating and advancing mock drafts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.models import UserRecord
from app.db.session import get_db
from app.services.draft_repository import DraftRepository

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class CreateDraftRequest(BaseModel):
    """Payload used to start a draft run."""

    controlled_team_id: str
    draft_year: int = Field(ge=2020, le=2100)


class SubmitPickRequest(BaseModel):
    """Payload used to submit a controlled-team selection."""

    player_id: str
    team_id: str


@router.post("", status_code=201)
def start_draft(
    payload: CreateDraftRequest,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Create a new draft run owned by the requesting user."""
    repository = DraftRepository(session)
    try:
        draft = repository.create(current_user.id, payload.controlled_team_id, payload.draft_year)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "draft_run_id": draft.id,
        "status": draft.status,
        "controlled_team_id": draft.controlled_team_id,
    }


@router.get("/{draft_id}")
def read_draft(
    draft_id: str,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Return the current state of a user-owned draft run."""
    repository = DraftRepository(session)
    try:
        return repository.state(repository.get_owned(draft_id, current_user.id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{draft_id}/picks", status_code=201)
def create_pick(
    draft_id: str,
    payload: SubmitPickRequest,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Submit a user pick for the controlled team."""
    repository = DraftRepository(session)
    try:
        draft = repository.get_owned(draft_id, current_user.id)
        if payload.team_id != draft.controlled_team_id:
            raise ValueError("Only the controlled team can be selected by the user")
        repository.add_pick(draft, payload.team_id, payload.player_id, "USER")
        session.commit()
        return repository.state(draft)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{draft_id}/auto-simulate")
def simulate_draft(
    draft_id: str,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Simulate non-controlled team picks until user action is needed."""
    repository = DraftRepository(session)
    try:
        draft = repository.get_owned(draft_id, current_user.id)
        repository.auto_simulate(draft)
        session.commit()
        return repository.state(draft)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
