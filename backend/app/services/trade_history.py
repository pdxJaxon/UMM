"""Historical draft-trade extraction and tendency persistence."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import HistoricalDraftTradeRecord, TeamDraftingTendencyRecord, TeamRecord


class DraftTradeHistoryProvider(Protocol):
    """Provider contract for normalized or raw historical draft-pick rows."""

    def load_draft_picks(self, seasons: list[int]) -> Any:
        """Return historical draft-pick rows for the requested seasons."""


class NflverseDraftTradeHistoryProvider:
    """Normalize ownership changes from nflverse draft-pick data."""

    def __init__(self, provider: DraftTradeHistoryProvider, source_name: str = "nflverse-draft-picks") -> None:
        self.provider = provider
        self.source_name = source_name

    def fetch(self, seasons: list[int]) -> list[dict[str, Any]]:
        """Return only rows with explicit original and selecting teams."""
        trades = []
        for row in _rows(self.provider.load_draft_picks(seasons)):
            draft_year = _integer(row, "draft_year", "season", "year")
            pick_number = _integer(row, "pick_number", "pick", "overall_pick")
            original_team = _team_value(row, "original_team_id", "original_team", "original_team_abbr", "from_team")
            selecting_team = _team_value(row, "team_id", "team", "team_abbr", "selecting_team", "to_team")
            if not draft_year or not pick_number or not original_team or not selecting_team or original_team == selecting_team:
                continue
            trade = {
                "draft_year": draft_year,
                "pick_number": pick_number,
                "moving_up_team": selecting_team,
                "moving_down_team": original_team,
                "source_name": self.source_name,
                "raw_payload": row,
            }
            _copy_actor(row, trade, "general_manager", "gm_id", "general_manager_id", "gm_name", "general_manager_name")
            _copy_actor(row, trade, "head_coach", "head_coach_id", "head_coach", "head_coach_name", "coach_name")
            trades.append(trade)
        return trades


class DraftTradeHistoryIngestionService:
    """Persist inferred trade events and refresh aggregate team tendencies."""

    def __init__(self, session: Session, provider: NflverseDraftTradeHistoryProvider) -> None:
        self.session = session
        self.provider = provider

    def refresh(self, seasons: list[int], observed_at: datetime | None = None) -> int:
        """Upsert events and replace aggregate trade-direction tendencies."""
        timestamp = observed_at or datetime.now(UTC)
        teams = {
            team.abbreviation.upper(): team.id
            for team in self.session.scalars(select(TeamRecord)).all()
        }
        events = 0
        for payload in self.provider.fetch(seasons):
            moving_up_team_id = teams.get(str(payload["moving_up_team"]).upper(), str(payload["moving_up_team"]))
            moving_down_team_id = teams.get(str(payload["moving_down_team"]).upper(), str(payload["moving_down_team"]))
            if self.session.get(TeamRecord, moving_up_team_id) is None or self.session.get(TeamRecord, moving_down_team_id) is None:
                continue
            existing = self.session.scalar(
                select(HistoricalDraftTradeRecord).where(
                    HistoricalDraftTradeRecord.source_name == payload["source_name"],
                    HistoricalDraftTradeRecord.draft_year == payload["draft_year"],
                    HistoricalDraftTradeRecord.pick_number == payload["pick_number"],
                )
            )
            if existing is None:
                self.session.add(HistoricalDraftTradeRecord(
                    draft_year=payload["draft_year"],
                    pick_number=payload["pick_number"],
                    moving_up_team_id=moving_up_team_id,
                    moving_down_team_id=moving_down_team_id,
                    general_manager_id=payload.get("general_manager_id"),
                    general_manager_name=payload.get("general_manager_name"),
                    head_coach_id=payload.get("head_coach_id"),
                    head_coach_name=payload.get("head_coach_name"),
                    source_name=payload["source_name"],
                    observed_at=timestamp,
                    raw_payload=payload["raw_payload"],
                ))
                events += 1
        self.session.flush()
        self._refresh_tendencies(timestamp)
        self.session.commit()
        return events

    def _refresh_tendencies(self, observed_at: datetime) -> None:
        """Write aggregate direction scores from all persisted historical events."""
        counts: dict[tuple[str, str | None, str | None], dict[str, int]] = defaultdict(lambda: {"trade_up": 0, "trade_down": 0})
        for event in self.session.scalars(select(HistoricalDraftTradeRecord)).all():
            counts[(event.moving_up_team_id, None, None)]["trade_up"] += 1
            counts[(event.moving_down_team_id, None, None)]["trade_down"] += 1
            if event.general_manager_id:
                counts[(event.moving_up_team_id, "gm", event.general_manager_id)]["trade_up"] += 1
                counts[(event.moving_down_team_id, "gm", event.general_manager_id)]["trade_down"] += 1
            if event.head_coach_id:
                counts[(event.moving_up_team_id, "head_coach", event.head_coach_id)]["trade_up"] += 1
                counts[(event.moving_down_team_id, "head_coach", event.head_coach_id)]["trade_down"] += 1
        for (team_id, actor_type, actor_id), directions in counts.items():
            total = directions["trade_up"] + directions["trade_down"]
            for tendency_type, count in directions.items():
                preference = round(50 + 50 * count / total, 2) if total else 0
                confidence = min(100, total * 20)
                tendency = self.session.scalar(
                    select(TeamDraftingTendencyRecord).where(
                        TeamDraftingTendencyRecord.team_id == team_id,
                        TeamDraftingTendencyRecord.draft_year.is_(None),
                        TeamDraftingTendencyRecord.tendency_type == tendency_type,
                        TeamDraftingTendencyRecord.source_name == "historical-trade-analysis",
                        TeamDraftingTendencyRecord.actor_type == actor_type,
                        TeamDraftingTendencyRecord.actor_id == actor_id,
                    )
                )
                if tendency is None:
                    tendency = TeamDraftingTendencyRecord(
                        team_id=team_id,
                        draft_year=None,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        actor_name=None,
                        tendency_type=tendency_type,
                        preference_score=preference,
                        confidence_score=confidence,
                        sample_size=count,
                        source_name="historical-trade-analysis",
                        rationale="Derived from explicit historical draft-pick ownership changes",
                        observed_at=observed_at,
                        raw_payload={"trade_up_count": directions["trade_up"], "trade_down_count": directions["trade_down"]},
                    )
                    self.session.add(tendency)
                else:
                    tendency.preference_score = preference
                    tendency.confidence_score = confidence
                    tendency.sample_size = count
                    tendency.observed_at = observed_at
                    tendency.raw_payload = {"trade_up_count": directions["trade_up"], "trade_down_count": directions["trade_down"]}


def _rows(value: Any) -> list[dict[str, Any]]:
    """Convert Polars, pandas, or list-like provider output to dictionaries."""
    if hasattr(value, "iter_rows"):
        return list(value.iter_rows(named=True))
    if hasattr(value, "to_dict"):
        try:
            return list(value.to_dict(orient="records"))
        except TypeError:
            pass
    return list(value)


def _integer(row: dict[str, Any], *names: str) -> int | None:
    """Return the first valid integer field from a source row."""
    for name in names:
        if row.get(name) not in (None, ""):
            try:
                return int(row[name])
            except (TypeError, ValueError):
                return None
    return None


def _team_value(row: dict[str, Any], *names: str) -> str | None:
    """Return a normalized team token from a source row."""
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _copy_actor(
    row: dict[str, Any],
    target: dict[str, Any],
    prefix: str,
    *names: str,
) -> None:
    """Copy an optional identity as a stable ID plus display name."""
    identifier = _team_value(row, *names[:3])
    if identifier:
        target[f"{prefix}_id"] = identifier
        target[f"{prefix}_name"] = _team_value(row, *names[3:]) or identifier