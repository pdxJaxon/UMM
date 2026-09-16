"""SQLAlchemy repository for persistent draft lifecycle operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DraftPickRecord, DraftRunRecord, PlayerRecord, TeamRecord

TEAM_ORDER = ("team-1", "team-2", "team-3")
PLAYER_ORDER = ("player-1", "player-2", "player-3", "player-4", "player-5")


class DraftRepository:
    """Persist and retrieve draft state using a SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        """Create a repository bound to one request-scoped database session."""
        self.session = session

    def create(self, user_id: str, controlled_team_id: str, draft_year: int) -> DraftRunRecord:
        """Create a draft after validating its owner and controlled team."""
        if self.session.get(TeamRecord, controlled_team_id) is None:
            raise ValueError("Controlled team does not exist")
        draft = DraftRunRecord(
            id=self._next_id("draft"),
            user_id=user_id,
            controlled_team_id=controlled_team_id,
            draft_year=draft_year,
            status="drafting",
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

    def add_pick(
        self,
        draft: DraftRunRecord,
        team_id: str,
        player_id: str,
        source: str,
    ) -> DraftPickRecord:
        """Persist a unique pick and enforce the current draft order."""
        picks = self._ordered_picks(draft.id)
        if player_id not in PLAYER_ORDER:
            raise ValueError("Player does not exist")
        if self.session.get(PlayerRecord, player_id) is None:
            raise ValueError("Player does not exist")
        if any(pick.player_id == player_id for pick in picks):
            raise ValueError("Player has already been selected")
        if team_id != self.current_team_id(len(picks)):
            raise ValueError("That team is not currently on the clock")
        pick_number = len(picks) + 1
        pick = DraftPickRecord(
            id=f"{draft.id}-pick-{pick_number}",
            draft_run_id=draft.id,
            pick_number=pick_number,
            round_number=((pick_number - 1) // len(TEAM_ORDER)) + 1,
            team_id=team_id,
            player_id=player_id,
            selection_source=source,
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
            player_id = next((candidate for candidate in PLAYER_ORDER if candidate not in selected), None)
            if player_id is None:
                draft.status = "completed"
                break
            self.add_pick(draft, self.current_team_id(len(picks)), player_id, "AUTO")
            picks = self._ordered_picks(draft.id)

    def state(self, draft: DraftRunRecord) -> dict[str, object]:
        """Return API-ready state for a persisted draft."""
        picks = self._ordered_picks(draft.id)
        return {
            "draft_run": {
                "id": draft.id,
                "user_id": draft.user_id,
                "controlled_team_id": draft.controlled_team_id,
                "season_year": draft.draft_year,
                "status": draft.status,
            },
            "current_pick_number": len(picks) + 1,
            "current_team_id": self.current_team_id(len(picks)),
            "picks": [
                {
                    "id": pick.id,
                    "draft_run_id": pick.draft_run_id,
                    "pick_number": pick.pick_number,
                    "round_number": pick.round_number,
                    "team_id": pick.team_id,
                    "player_id": pick.player_id,
                    "selection_source": pick.selection_source,
                }
                for pick in picks
            ],
        }

    @staticmethod
    def current_team_id(pick_count: int) -> str:
        """Return the team assigned to the next pick."""
        if pick_count >= len(PLAYER_ORDER):
            return ""
        return TEAM_ORDER[pick_count % len(TEAM_ORDER)]

    def _ordered_picks(self, draft_id: str) -> list[DraftPickRecord]:
        """Load a draft's picks in immutable pick order."""
        statement = (
            select(DraftPickRecord)
            .where(DraftPickRecord.draft_run_id == draft_id)
            .order_by(DraftPickRecord.pick_number)
        )
        return list(self.session.scalars(statement))

    def _next_id(self, prefix: str) -> str:
        """Generate a collision-resistant identifier within the current database."""
        count = self.session.query(DraftRunRecord).count()
        return f"{prefix}-{count + 1}"
