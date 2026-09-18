"""Provider-agnostic ingestion service for frequently changing prospect data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.db.models import CollegeRecord, PlayerAthleticScoreRecord, PlayerMeasurementRecord, PlayerRecord


class ProspectProvider(Protocol):
    """Contract implemented by an approved prospect data provider."""

    def fetch(self, draft_year: int) -> list[dict[str, Any]]:
        """Return normalized prospect payloads for a draft year."""


class ProspectIngestionService:
    """Upsert prospect profiles while preserving dated source snapshots."""

    def __init__(self, session: Session, provider: ProspectProvider) -> None:
        """Create an ingestion service for one database transaction and provider."""
        self.session = session
        self.provider = provider

    def refresh(self, draft_year: int, observed_at: datetime | None = None) -> int:
        """Ingest a provider batch and return the number of processed prospects."""
        timestamp = observed_at or datetime.now(UTC)
        processed = 0
        for payload in self.provider.fetch(draft_year):
            self._upsert_prospect(payload, draft_year, timestamp)
            processed += 1
        self.session.commit()
        return processed

    def _upsert_prospect(self, payload: dict[str, Any], draft_year: int, observed_at: datetime) -> None:
        """Update stable profile fields and append new source snapshots."""
        player_id = str(payload["id"])
        self._ensure_college(payload)
        player = self.session.get(PlayerRecord, player_id)
        if player is None:
            player = PlayerRecord(
                id=player_id,
                first_name=payload["first_name"],
                last_name=payload["last_name"],
                position=payload["position"],
                college_id=payload["college_id"],
                draft_year=draft_year,
            )
            self.session.add(player)
        else:
            for field in ("first_name", "last_name", "position", "college_id"):
                if field in payload:
                    setattr(player, field, payload[field])

        measurement = payload.get("measurements")
        if measurement:
            self.session.add(
                PlayerMeasurementRecord(
                    player_id=player_id,
                    observed_at=observed_at,
                    source_name=measurement["source_name"],
                    source_record_id=measurement.get("source_record_id"),
                    age_years=measurement.get("age_years"),
                    height_inches=measurement.get("height_inches"),
                    weight_lbs=measurement.get("weight_lbs"),
                    hand_inches=measurement.get("hand_inches"),
                    arm_inches=measurement.get("arm_inches"),
                    raw_payload=measurement,
                )
            )

        for score in payload.get("athletic_scores", []):
            self.session.add(
                PlayerAthleticScoreRecord(
                    player_id=player_id,
                    observed_at=observed_at,
                    source_name=score["source_name"],
                    metric_name=score["metric_name"],
                    score=score.get("score"),
                    score_scale=score.get("score_scale"),
                    raw_payload=score,
                )
            )

    def _ensure_college(self, payload: dict[str, Any]) -> None:
        """Create a minimal college reference when a provider introduces a new school."""
        college_id = str(payload["college_id"])
        if self.session.get(CollegeRecord, college_id) is not None:
            return
        college_name = str(payload.get("college_name") or college_id.replace("-", " ").title())
        abbreviations = {value for (value,) in self.session.query(CollegeRecord.abbreviation).all()}
        abbreviation = college_id[:20]
        suffix = 2
        while abbreviation in abbreviations:
            suffix_text = f"-{suffix}"
            abbreviation = f"{college_id[:20 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        self.session.add(
            CollegeRecord(
                id=college_id,
                name=college_name,
                abbreviation=abbreviation,
                conference="Unknown",
                division="FBS",
                logo_url="",
                official_url="",
            )
        )