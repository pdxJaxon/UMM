"""REST endpoints for creating and advancing mock drafts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.models import DraftPickRecord, PlayerRecord, TeamRecord, UserRecord
from app.db.session import get_db
from app.services.draft_repository import DraftRepository
from app.services.llm_prediction import (
    OpenAICompatiblePredictionProvider, PredictionContext,
    RecommendationNotConfiguredError, predict_pick,
)
from app.services.prospect_pool import pool_filter

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
    reviewed_recommendation_id: str
    manual_override: bool


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
        "eligible_players": repository.eligible_players(draft),
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
        expected_team_id = repository.current_team_id(len(draft.picks), draft.draft_order)
        if payload.team_id != expected_team_id:
            raise ValueError("Prediction requested for a team that is not on the clock")
        team = session.get(TeamRecord, payload.team_id)
        if team is None:
            raise ValueError("Prediction team does not exist")
        candidate_ids = [candidate.get("player_id") for candidate in payload.candidates]
        if any(not isinstance(player_id, str) or not player_id for player_id in candidate_ids):
            raise ValueError("Each prediction candidate must include a player ID")
        eligible_candidate_ids = set(session.scalars(
            select(PlayerRecord.id).where(
                PlayerRecord.id.in_(candidate_ids),
                pool_filter(draft.draft_year, draft.prospect_snapshot_id),
                ~PlayerRecord.id.in_(
                    select(DraftPickRecord.player_id).where(DraftPickRecord.draft_run_id == draft.id)
                ),
            )
        ))
        if eligible_candidate_ids != set(candidate_ids):
            raise ValueError("Prediction candidates must be eligible and not already selected for this draft")
        team_randomness = draft.randomness_overrides.get(payload.team_id, float(team.randomness_score or 50))
        result = predict_pick(
            PredictionContext(
                team_id=payload.team_id,
                team_name=team.name,
                draft_year=draft.draft_year,
                pick_number=len(draft.picks) + 1,
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


@router.post("/{draft_id}/recommendation")
def recommend_current_pick(
    draft_id: str,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Return the current model decision using only server-side draft evidence."""
    provider = OpenAICompatiblePredictionProvider()
    try:
        repository = DraftRepository(session, prediction_provider=provider)
        return repository.recommend(repository.get_owned(draft_id, current_user.id))
    except RecommendationNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "llm_required",
            "message": "LLM selection is required. No pick was made; configure or restore the LLM provider and retry.",
        }) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        provider.close()


@router.post("/{draft_id}/picks", status_code=201)
def create_pick(
    draft_id: str,
    payload: SubmitPickRequest,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Require an LLM decision before recording the controlled-team pick or override."""
    provider = OpenAICompatiblePredictionProvider()
    repository = DraftRepository(session, prediction_provider=provider)
    try:
        draft = repository.get_owned(draft_id, current_user.id)
        if payload.team_id != draft.controlled_team_id:
            raise ValueError("Only the controlled team can be selected by the user")
        prediction = repository.recommend(draft)
        recommended_id = str(prediction["recommended"]["player_id"])
        if recommended_id != payload.reviewed_recommendation_id:
            raise HTTPException(status_code=409, detail={
                "code": "recommendation_changed",
                "message": "The LLM decision changed. Review the updated decision and confirm your pick.",
                "recommendation": prediction,
                "manual_override": payload.manual_override,
            })
        manual_override = payload.manual_override
        metadata = {
            "mode": "llm",
            "provider": prediction["provider"],
            "model": prediction["model"],
            "prompt_version": prediction["prompt_version"],
            "confidence": prediction["confidence"],
            "randomness": prediction["randomness"],
            "llm_selected_player_id": recommended_id,
            "selected_player_id": payload.player_id,
            "manual_override": manual_override,
            "alternatives": prediction["alternatives"],
            "reasoning_factors": prediction["reasoning_factors"],
            "evidence": prediction["evidence"],
            "candidates": prediction["candidates"],
        }
        repository.add_pick(
            draft,
            payload.team_id,
            payload.player_id,
            "USER_OVERRIDE" if manual_override else "LLM",
            float(prediction["randomness"]),
            metadata,
        )
        session.commit()
        return repository.state(draft)
    except RecommendationNotConfiguredError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail={
            "code": "llm_required",
            "message": "LLM selection is required. No pick was made; configure or restore the LLM provider and retry.",
        }) from exc
    except LookupError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        session.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=f"LLM selection failed; no pick was made: {exc}") from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        provider.close()


@router.post("/{draft_id}/auto-simulate")
def simulate_draft(
    draft_id: str,
    max_picks: int | None = Query(default=None, ge=1, le=32),
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Simulate LLM-selected picks, stopping for user action when needed."""
    provider = OpenAICompatiblePredictionProvider()
    repository = DraftRepository(session, prediction_provider=provider)
    try:
        draft = repository.get_owned(draft_id, current_user.id)
        repository.auto_simulate(draft, max_picks=max_picks)
        session.commit()
        return repository.state(draft)
    except RecommendationNotConfiguredError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail={
            "code": "llm_required",
            "message": "LLM selection is required. No picks were saved; configure or restore the LLM provider and retry.",
        }) from exc
    except LookupError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        session.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        provider.close()
