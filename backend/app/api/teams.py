"""Public reference-data endpoints for NFL teams."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TeamDraftingTendencyRecord, TeamNeedRecord, TeamRecord
from app.db.session import get_db

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