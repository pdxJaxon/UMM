"""Conservative scraper for an authorized PFF Big Board HTML response.

This adapter performs one normal HTTP request and parses data already present in
the response. It does not automate login, bypass paywalls, evade bot controls,
or submit credentials. Use it only where PFF's terms and access permissions
allow automated retrieval.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings


class PFFBigBoardScraper:
    """Fetch and normalize an authorized PFF Big Board page."""

    def __init__(
        self,
        page_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        """Create a scraper using configured URL and optional API bearer key."""
        self.page_url = page_url or settings.pff_big_board_url
        self.api_key = api_key if api_key is not None else settings.pff_api_key
        self.client = client or httpx.Client(timeout=timeout_seconds or settings.pff_request_timeout_seconds)

    def fetch(self, draft_year: int) -> list[dict[str, Any]]:
        """Fetch one Big Board page and return normalized prospect records."""
        response = self.client.get(
            self.page_url,
            params={"season": draft_year},
            headers=self._headers(),
        )
        response.raise_for_status()
        return self.parse_html(response.text, draft_year)

    @staticmethod
    def parse_html(html: str, draft_year: int) -> list[dict[str, Any]]:
        """Parse embedded JSON or semantic table rows from a Big Board response."""
        records = PFFBigBoardScraper._parse_embedded_json(html, draft_year)
        if records:
            return records
        soup = BeautifulSoup(html, "html.parser")
        rows = []
        for row in soup.select("tr[data-player-id], tr.player-row, [data-player-id]"):
            player_id = row.get("data-player-id")
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td, [data-field]")]
            if not player_id or len(cells) < 3:
                continue
            rows.append(
                {
                    "id": str(player_id),
                    "first_name": cells[1].split(" ", 1)[0],
                    "last_name": cells[1].split(" ", 1)[-1],
                    "position": cells[2],
                    "college_id": cells[3] if len(cells) > 3 else "unknown",
                    "draft_year": draft_year,
                    "pff_rank": _number(cells[0]),
                    "measurements": {"source_name": "pff-big-board", "raw_payload": {"cells": cells}},
                }
            )
        if not rows:
            raise ValueError("No structured PFF Big Board records found in response")
        return rows

    def _headers(self) -> dict[str, str]:
        """Return ordinary request headers without emulating a browser login."""
        headers = {"Accept": "text/html,application/xhtml+xml", "User-Agent": "UMockMe-prospect-import/1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _parse_embedded_json(html: str, draft_year: int) -> list[dict[str, Any]]:
        """Parse common JSON state containers used by server-rendered applications."""
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.select("script[type='application/json'], script#__NEXT_DATA__"):
            try:
                payload = json.loads(script.string or script.get_text())
            except json.JSONDecodeError:
                continue
            records = _find_player_list(payload)
            if records:
                return [PFFBigBoardScraper._normalize_record(record, draft_year) for record in records]
        return []

    @staticmethod
    def _normalize_record(record: dict[str, Any], draft_year: int) -> dict[str, Any]:
        """Normalize common Big Board JSON field names."""
        player_id = record.get("id") or record.get("playerId") or record.get("personId")
        name = record.get("name") or f"{record.get('firstName', '')} {record.get('lastName', '')}".strip()
        first_name, _, last_name = name.partition(" ")
        if not player_id or not name:
            raise ValueError("PFF Big Board record requires player id and name")
        return {
            "id": str(player_id),
            "first_name": first_name,
            "last_name": last_name,
            "position": record.get("position") or record.get("pos") or "UNKNOWN",
            "college_id": record.get("college_id") or record.get("collegeSlug") or record.get("college") or "unknown",
            "draft_year": draft_year,
            "pff_rank": record.get("rank") or record.get("overallRank"),
            "measurements": {
                "source_name": "pff-big-board",
                "height_inches": record.get("height_inches") or record.get("height"),
                "weight_lbs": record.get("weight_lbs") or record.get("weight"),
                "raw_payload": record,
            },
        }


def _find_player_list(value: Any) -> list[dict[str, Any]] | None:
    """Recursively find a list of dictionary records that looks player-like."""
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        if any(item.get("id") or item.get("playerId") or item.get("personId") for item in value):
            return value
    if isinstance(value, dict):
        for child in value.values():
            result = _find_player_list(child)
            if result:
                return result
    return None


def _number(value: str) -> int | float | None:
    """Convert a displayed rank value to a numeric value when possible."""
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return None
    number = float(match.group())
    return int(number) if number.is_integer() else number