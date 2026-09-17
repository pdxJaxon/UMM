"""SQLAlchemy repository for persistent draft lifecycle operations."""

from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DraftPickRecord, DraftRunRecord, PlayerRecord, TeamBoardEntryRecord, TeamBoardRecord, TeamRecord
from app.services.ranking_service import select_with_team_randomness

TEAM_ORDER = ("team-1", "team-2", "team-3")
PLAYER_ORDER = ("player-1", "player-2", "player-3", "player-4", "player-5")


class DraftRepository:
    """Persist and retrieve draft state using a SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        """Create a repository bound to one request-scoped database session."""
        self.session = session

    def create(self, user_id: str, controlled_team_id: str, draft_year: int, randomness_overrides: dict[str, float] | None = None) -> DraftRunRecord:
        """Create a draft after validating its team and randomness overrides."""
        if self.session.get(TeamRecord, controlled_team_id) is None:
            raise ValueError("Controlled team does not exist")
        overrides = randomness_overrides or {}
        if any(not 0 <= float(value) <= 100 for value in overrides.values()):
            raise ValueError("Randomness overrides must be between 0 and 100")
        draft = DraftRunRecord(
            id=self._next_id("draft"), user_id=user_id, controlled_team_id=controlled_team_id,
            draft_year=draft_year, status="drafting", randomness_overrides=overrides,
        )
        self.session.add(draft)
        self.session.flush()
        return draft

    def get_owned(self, draft_id: str, user_id: str) -> DraftRunRecord:
        """Return a draft only when it exists and belongs to the requesting user."""
        draft = self.session.get(DraftRunRecord, draft_id)
        if draft is None:
            raise LookupError("Draft not found")
        if draft.user_id != user_id:
            raise PermissionError("Draft access denied")
        return draft

    def add_pick(self, draft: DraftRunRecord, team_id: str, player_id: str, source: str, randomness_factor: float = 0) -> DraftPickRecord:
        """Persist a unique pick and enforce the current draft order."""
        picks = self._ordered_picks(draft.id)
        if player_id not in PLAYER_ORDER or self.session.get(PlayerRecord, player_id) is None:
            raise ValueError("Player does not exist")
        if any(pick.player_id == player_id for pick in picks):
            raise ValueError("Player has already been selected")
        if team_id != self.current_team_id(len(picks)):
            raise ValueError("That team is not currently on the clock")
        pick_number = len(picks) + 1
        pick = DraftPickRecord(
            id=f"{draft.id}-pick-{pick_number}", draft_run_id=draft.id, pick_number=pick_number,
            round_number=((pick_number - 1) // len(TEAM_ORDER)) + 1, team_id=team_id,
            player_id=player_id, selection_source=source, randomness_factor=randomness_factor,
        )
        self.session.add(pick)
        if pick_number >= len(PLAYER_ORDER):
            draft.status = "completed"
        self.session.flush()
        return pick

    def auto_simulate(self, draft: DraftRunRecord) -> None:
        """Select available players until the controlled team is on the clock."""
        picks = self._ordered_picks(draft.id)
        while draft.status != "completed" and self.current_team_id(len(picks)) != draft.controlled_team_id:
            selected = {pick.player_id for pick in picks}
            team_id = self.current_team_id(len(picks))
            remaining = self._available_board_candidates(draft, team_id, selected)
            if not remaining:
                remaining = [candidate for candidate in PLAYER_ORDER if candidate not in selected]
            if not remaining:
                draft.status = "completed"
                break
            team = self.session.get(TeamRecord, team_id)
            baseline = float(team.randomness_score or 0) if team else 50.0
            randomness = draft.randomness_overrides.get(team_id, baseline)
            player_id, applied_randomness = select_with_team_randomness(remaining, randomness, random.Random())
            self.add_pick(draft, team_id, player_id, "AUTO", applied_randomness)
            picks = self._ordered_picks(draft.id)

    def state(self, draft: DraftRunRecord) -> dict[str, object]:
        """Return API-ready state for a persisted draft."""
        picks = self._ordered_picks(draft.id)
        return {
            "draft_run": {"id": draft.id, "user_id": draft.user_id, "controlled_team_id": draft.controlled_team_id, "season_year": draft.draft_year, "status": draft.status, "randomness_overrides": draft.randomness_overrides},
            "current_pick_number": len(picks) + 1,
            "current_team_id": self.current_team_id(len(picks)),
            "picks": [{"id": p.id, "draft_run_id": p.draft_run_id, "pick_number": p.pick_number, "round_number": p.round_number, "team_id": p.team_id, "player_id": p.player_id, "selection_source": p.selection_source, "randomness_factor": float(p.randomness_factor)} for p in picks],
        }

    @staticmethod
    def current_team_id(pick_count: int) -> str:
        """Return the team assigned to the next pick."""
        return "" if pick_count >= len(PLAYER_ORDER) else TEAM_ORDER[pick_count % len(TEAM_ORDER)]

    def _ordered_picks(self, draft_id: str) -> list[DraftPickRecord]:
        """Load a draft's picks in immutable pick order."""
        statement = select(DraftPickRecord).where(DraftPickRecord.draft_run_id == draft_id).order_by(DraftPickRecord.pick_number)
        return list(self.session.scalars(statement))

    def _available_board_candidates(
        self,
        draft: DraftRunRecord,
        team_id: str,
        selected: set[str],
    ) -> list[str]:
        """Return available players from the latest generated team board."""
        board = self.session.scalar(
            select(TeamBoardRecord)
            .where(
                TeamBoardRecord.team_id == team_id,
                TeamBoardRecord.draft_year == draft.draft_year,
                TeamBoardRecord.board_type == "default",
            )
            .order_by(TeamBoardRecord.version.desc())
            .limit(1)
        )
        if board is None:
            return []
        entries = self.session.scalars(
            select(TeamBoardEntryRecord)
            .where(
                TeamBoardEntryRecord.board_id == board.id,
                TeamBoardEntryRecord.is_active.is_(True),
            )
            .order_by(TeamBoardEntryRecord.rank_position)
        ).all()
        return [entry.player_id for entry in entries if entry.player_id not in selected]

    def _next_id(self, prefix: str) -> str:
        """Generate a collision-resistant identifier within the current database."""
        return f"{prefix}-{self.session.query(DraftRunRecord).count() + 1}"
