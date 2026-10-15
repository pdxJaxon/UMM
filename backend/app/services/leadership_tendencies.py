"""Blend franchise and current-regime tendencies for draft decisions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TeamDraftingTendencyRecord, TeamLeadershipRecord


def get_effective_tendencies(session: Session, team_id: str, draft_year: int) -> list[dict[str, object]]:
    """Return franchise and leadership tendencies blended for one draft year."""
    franchise_rows = session.scalars(
        select(TeamDraftingTendencyRecord).where(
            TeamDraftingTendencyRecord.team_id == team_id,
            TeamDraftingTendencyRecord.is_active.is_(True),
            TeamDraftingTendencyRecord.actor_id.is_(None),
            (TeamDraftingTendencyRecord.draft_year == draft_year) | (TeamDraftingTendencyRecord.draft_year.is_(None)),
        )
    ).all()
    leadership = session.scalars(
        select(TeamLeadershipRecord).where(
            TeamLeadershipRecord.team_id == team_id,
            TeamLeadershipRecord.is_active.is_(True),
            TeamLeadershipRecord.start_year <= draft_year,
            (TeamLeadershipRecord.end_year.is_(None)) | (TeamLeadershipRecord.end_year >= draft_year),
        )
    ).all()
    actor_ids = [leader.person_id for leader in leadership]
    actor_rows = []
    if actor_ids:
        actor_rows = session.scalars(
            select(TeamDraftingTendencyRecord).where(
                TeamDraftingTendencyRecord.actor_id.in_(actor_ids),
                TeamDraftingTendencyRecord.is_active.is_(True),
                (TeamDraftingTendencyRecord.draft_year == draft_year) | (TeamDraftingTendencyRecord.draft_year.is_(None)),
            )
        ).all()

    grouped: dict[tuple[object, ...], list[tuple[Mapping[str, object], float]]] = defaultdict(list)
    for tendency in franchise_rows:
        grouped[_key(tendency)].append((_as_mapping(tendency), _weight("franchise", tendency.tendency_type)))
    role_by_actor = {leader.person_id: leader.role_type for leader in leadership}
    for tendency in actor_rows:
        role_type = role_by_actor.get(tendency.actor_id)
        if role_type in {"gm", "head_coach"}:
            grouped[_key(tendency)].append((_as_mapping(tendency), _weight(role_type, tendency.tendency_type)))

    effective = []
    for rows in grouped.values():
        total_weight = sum(weight for _, weight in rows)
        if total_weight <= 0:
            continue
        score = sum(float(row["preference_score"]) * weight for row, weight in rows) / total_weight
        confidence = sum(float(row["confidence_score"]) * weight for row, weight in rows) / total_weight
        sample_size = sum(int(row.get("sample_size", 0)) for row, _ in rows)
        primary = dict(rows[0][0])
        primary.update({
            "preference_score": round(score, 2),
            "confidence_score": round(confidence, 2),
            "sample_size": sample_size,
            "scope": "franchise-plus-regime" if len(rows) > 1 else str(primary.get("actor_type") or "franchise"),
            "components": [
                {
                    "actor_type": row.get("actor_type") or "franchise",
                    "actor_id": row.get("actor_id"),
                    "actor_name": row.get("actor_name"),
                    "weight": weight,
                    "preference_score": row["preference_score"],
                    "confidence_score": row["confidence_score"],
                }
                for row, weight in rows
            ],
        })
        effective.append(primary)
    return effective


def _key(tendency: TeamDraftingTendencyRecord) -> tuple[object, ...]:
    """Group equivalent directional or player-fit tendencies."""
    return (tendency.tendency_type, tendency.position_code, tendency.metric_name, tendency.target_value)


def _as_mapping(tendency: TeamDraftingTendencyRecord) -> dict[str, object]:
    """Convert a tendency record into the model-safe shape used by scoring."""
    return {
        "tendency_type": tendency.tendency_type,
        "position_code": tendency.position_code,
        "metric_name": tendency.metric_name,
        "target_value": tendency.target_value,
        "preference_score": float(tendency.preference_score),
        "confidence_score": float(tendency.confidence_score),
        "sample_size": tendency.sample_size,
        "source_name": tendency.source_name,
        "rationale": tendency.rationale,
        "actor_type": tendency.actor_type,
        "actor_id": tendency.actor_id,
        "actor_name": tendency.actor_name,
        "is_active": tendency.is_active,
    }


def _weight(actor_type: str, tendency_type: str) -> float:
    """Weight franchise, GM, and coach history by decision responsibility."""
    if actor_type == "franchise":
        return 0.60
    if tendency_type in {"trade_up", "trade_down"}:
        return 0.25 if actor_type == "gm" else 0.15
    return 0.15 if actor_type == "gm" else 0.25