"""Prospect normalization adapter for nflverse combine and player data."""

from __future__ import annotations

import re
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
            player_id = str(row.get("player_id") or row.get("gsis_id") or row.get("id") or row.get("pfr_id") or row.get("cfb_id") or "")
            if not player_id:
                continue
            player = player_rows.get(player_id) or player_rows.get(str(row.get("gsis_id"))) or {}
            first_name, last_name = _names(row, player)
            college = row.get("college_name") or row.get("college") or row.get("school") or player.get("college_name") or player.get("college")
            normalized.append(
                {
                    "id": player_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "position": row.get("pos") or player.get("position") or "UNKNOWN",
                    "college_id": _college_id(college),
                    "college_name": str(college or "Unknown"),
                    "draft_year": draft_year,
                    "measurements": {
                        "source_name": "nflverse-combine",
                        "source_record_id": player_id,
                        "height_inches": _height_inches(row.get("height") or row.get("height_inches") or row.get("ht")),
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


def _names(row: dict[str, Any], player: dict[str, Any]) -> tuple[str, str]:
    """Resolve split or full player names from nflverse schemas."""
    first_name = row.get("first_name") or player.get("first_name")
    last_name = row.get("last_name") or player.get("last_name")
    if not first_name and not last_name:
        parts = str(row.get("player_name") or player.get("display_name") or "Unknown Prospect").split()
        first_name, last_name = (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (parts[0], "Prospect")
    return str(first_name or "Unknown"), str(last_name or "Prospect")


def _height_inches(value: Any) -> Any:
    """Convert nflverse feet-inch strings to the numeric schema value."""
    if not isinstance(value, str) or "-" not in value:
        return value
    match = re.fullmatch(r"(\d+)-(\d+)", value.strip())
    return int(match.group(1)) * 12 + int(match.group(2)) if match else value
