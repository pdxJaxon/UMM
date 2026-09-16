"""Approved-endpoint adapter for importing permitted PFF prospect data.

This module intentionally does not automate browser login or scrape authenticated
pages. Configure it only with an endpoint or export service that PFF permits the
application to access.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class PFFProvider:
    """Fetch and normalize prospect records from an approved PFF JSON endpoint."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_token: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        """Create a provider using environment-backed configuration by default."""
        self.endpoint = endpoint if endpoint is not None else settings.pff_data_url
        self.api_token = api_token if api_token is not None else settings.pff_api_token
        self.timeout_seconds = timeout_seconds or settings.pff_request_timeout_seconds
        self.client = client or httpx.Client(timeout=self.timeout_seconds)

    def fetch(self, draft_year: int) -> list[dict[str, Any]]:
        """Fetch a draft-year batch and normalize it for prospect ingestion."""
        if not self.endpoint:
            raise RuntimeError("PFF_DATA_URL is not configured")
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        response = self.client.get(self.endpoint, params={"draft_year": draft_year}, headers=headers)
        response.raise_for_status()
        payload = response.json()
        records = payload.get("players", []) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("PFF response must contain a players list")
        return [self._normalize(record, draft_year) for record in records]

    @staticmethod
    def _normalize(record: dict[str, Any], draft_year: int) -> dict[str, Any]:
        """Map an approved PFF response record to the ingestion schema."""
        player_id = record.get("id") or record.get("player_id")
        college_id = record.get("college_id") or record.get("college_slug")
        if not player_id or not college_id:
            raise ValueError("PFF prospect records require id and college_id")
        measurement = record.get("measurements", {})
        return {
            "id": str(player_id),
            "first_name": record.get("first_name", ""),
            "last_name": record.get("last_name", ""),
            "position": record.get("position", "UNKNOWN"),
            "college_id": str(college_id),
            "draft_year": draft_year,
            "measurements": {
                "source_name": "pff",
                "source_record_id": str(player_id),
                "age_years": record.get("age_years", measurement.get("age_years")),
                "height_inches": record.get("height_inches", measurement.get("height_inches")),
                "weight_lbs": record.get("weight_lbs", measurement.get("weight_lbs")),
                "hand_inches": record.get("hand_inches", measurement.get("hand_inches")),
                "arm_inches": record.get("arm_inches", measurement.get("arm_inches")),
                "raw_payload": record,
            },
            "athletic_scores": [
                {
                    "source_name": "pff",
                    "metric_name": "pff_grade",
                    "score": record.get("pff_grade"),
                    "score_scale": "pff",
                    "raw_payload": {"pff_grade": record.get("pff_grade")},
                }
            ]
            if record.get("pff_grade") is not None
            else [],
        }

    def close(self) -> None:
        """Close the internally owned HTTP client."""
        self.client.close()