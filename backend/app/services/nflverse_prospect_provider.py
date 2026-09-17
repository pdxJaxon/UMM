"""Prospect normalization adapter for nflverse combine and player data."""

from __future__ import annotations

from typing import Any

from app.services.nflverse_provider import NflverseProvider
from app.services.prospect_ingestion import ProspectProvider


class NflverseProspectProvider(ProspectProvider):
    """Convert nflreadpy player and combine records to the ingestion contract."""

    def __init__(self, provider: NflverseProvider | None = None) -> None:
        """Create an adapter around the maintained nflverse provider."""
        self.provider = provider or NflverseProvider()

    def fetch(self, draft_year: int) -> list[dict[str, Any]]:
        """Load and normalize combine records for the requested draft year."""
        combine = self.provider.load_combine([draft_year])
        players = self.provider.load_players()
        player_rows = {str(row.get("id")): row for row in _rows(players)}
        normalized = []
        for row in _rows(combine):
            player_id = str(row.get("player_id") or row.get("gsis_id") or row.get("id") or "")
            if not player_id:
                continue
            player = player_rows.get(player_id, {})
            college = row.get("college_name") or row.get("college") or player.get("college_name") or player.get("college")
            normalized.append(
                {
                    "id": player_id,
                    "first_name": row.get("first_name") or player.get("first_name") or "Unknown",
                    "last_name": row.get("last_name") or player.get("last_name") or "Prospect",
                    "position": row.get("pos") or player.get("position") or "UNKNOWN",
                    "college_id": _college_id(college),
                    "draft_year": draft_year,
                    "measurements": {
                        "source_name": "nflverse-combine",
                        "source_record_id": player_id,
                        "height_inches": row.get("height") or row.get("height_inches"),
                        "weight_lbs": row.get("weight") or row.get("weight_lbs"),
                        "raw_payload": row,
                    },
                }
            )
        return normalized


def _rows(value: Any) -> list[dict[str, Any]]:
    """Convert Polars, pandas, or list-like data into dictionaries."""
    if hasattr(value, "iter_rows"):
        return list(value.iter_rows(named=True))
    if hasattr(value, "to_dict"):
        try:
            return list(value.to_dict(orient="records"))
        except TypeError:
            pass
    return list(value)


def _college_id(value: Any) -> str:
    """Create the project college identifier expected by the relational schema."""
    return str(value or "unknown").lower().replace(" ", "-")
