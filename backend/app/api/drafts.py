"""REST endpoints for creating and advancing mock drafts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.models import TeamRecord, UserRecord
from app.db.session import get_db
from app.services.draft_repository import DraftRepository
from app.services.llm_prediction import OpenAICompatiblePredictionProvider, PredictionContext, predict_pick

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class CreateDraftRequest(BaseModel):
    """Payload used to start a draft run."""

    controlled_team_id: str
    draft_year: int = Field(ge=2020, le=2100)
    overall_randomness: float = Field(default=50, ge=0, le=100)
    randomness_overrides: dict[str, float] = Field(default_factory=dict)


class SubmitPickRequest(BaseModel):
    """Payload used to submit a controlled-team selection."""

    player_id: str
    team_id: str


class PredictPickRequest(BaseModel):
    """Evidence payload supplied to the model for the current team pick."""

    team_id: str
    pick_number: int = Field(ge=1)
    candidates: list[dict[str, object]] = Field(min_length=1)
    team_needs: list[dict[str, object]] = Field(default_factory=list)
    team_tendencies: list[dict[str, object]] = Field(default_factory=list)


@router.post("", status_code=201)
def start_draft(
    payload: CreateDraftRequest,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Create a new draft run owned by the requesting user."""
    repository = DraftRepository(session)
    try:
        draft = repository.create(
            current_user.id,
            payload.controlled_team_id,
            payload.draft_year,
            payload.randomness_overrides,
            payload.overall_randomness,
        )
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


@router.post("/{draft_id}/prediction")
def predict_current_pick(
    draft_id: str,
    payload: PredictPickRequest,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Ask the configured frontier model to select one available player."""
    repository = DraftRepository(session)
    try:
        draft = repository.get_owned(draft_id, current_user.id)
        expected_team_id = repository.current_team_id(len(draft.picks))
        if payload.team_id != expected_team_id:
            raise ValueError("Prediction requested for a team that is not on the clock")
        team = session.get(TeamRecord, payload.team_id)
        if team is None:
            raise ValueError("Prediction team does not exist")
        team_randomness = draft.randomness_overrides.get(payload.team_id, float(team.randomness_score or 50))
        result = predict_pick(
            PredictionContext(
                team_id=payload.team_id,
                team_name=team.name,
                draft_year=draft.draft_year,
                pick_number=payload.pick_number,
                candidates=tuple(payload.candidates),
                team_needs=tuple(payload.team_needs),
                team_tendencies=tuple(payload.team_tendencies),
                overall_randomness=float(draft.overall_randomness),
                team_randomness=float(team_randomness),
            ),
            OpenAICompatiblePredictionProvider(),
        )
        return {
            "team_id": result.team_id,
            "pick_number": result.pick_number,
            "selected_player_id": result.selected_player_id,
            "confidence": result.confidence,
            "alternatives": result.alternatives,
            "reasoning_factors": result.reasoning_factors,
            "evidence": result.evidence,
            "provider": result.provider,
            "model": result.model,
            "prompt_version": result.prompt_version,
            "randomness": result.randomness,
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
