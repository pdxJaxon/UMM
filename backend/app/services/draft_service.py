"""Application service for mock draft lifecycle operations."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.models.draft_pick import DraftPick
from app.models.draft_run import DraftRun

_TEAM_ORDER = ["team-1", "team-2", "team-3"]
_PLAYER_ORDER = ["player-1", "player-2", "player-3", "player-4", "player-5"]
_DRAFT_RUNS: dict[str, DraftRun] = {}
_DRAFT_PICKS: dict[str, list[DraftPick]] = {}


def reset_draft_store() -> None:
    """Clear in-memory draft state for isolated tests and local development."""
    _DRAFT_RUNS.clear()
    _DRAFT_PICKS.clear()


def create_draft(user_id: str, controlled_team_id: str, draft_year: int) -> DraftRun:
    """Create a draft run after validating the selected controlled team."""
    if controlled_team_id not in _TEAM_ORDER:
        raise ValueError("Controlled team does not exist")

    draft_id = f"draft-{len(_DRAFT_RUNS) + 1}"
    draft = DraftRun(
        id=draft_id,
        user_id=user_id,
        controlled_team_id=controlled_team_id,
        season_year=draft_year,
    )
    _DRAFT_RUNS[draft_id] = draft
    _DRAFT_PICKS[draft_id] = []
    return draft


def get_draft(draft_id: str, user_id: str) -> dict[str, Any]:
    """Return a user-owned draft and its current pick context."""
    draft = _get_owned_draft(draft_id, user_id)
    picks = _DRAFT_PICKS[draft_id]
    return {
        "draft_run": asdict(draft),
        "current_pick_number": len(picks) + 1,
        "current_team_id": _current_team_id(len(picks)),
        "picks": [asdict(pick) for pick in picks],
    }


def submit_pick(
    draft_id: str,
    user_id: str,
    player_id: str,
    team_id: str,
) -> dict[str, Any]:
    """Record a controlled-team pick and return the updated draft state."""
    draft = _get_owned_draft(draft_id, user_id)
    picks = _DRAFT_PICKS[draft_id]
    if draft.status == "completed":
        raise ValueError("Draft is already completed")
    if team_id != draft.controlled_team_id:
        raise ValueError("Only the controlled team can be selected by the user")
    if team_id != _current_team_id(len(picks)):
        raise ValueError("That team is not currently on the clock")
    _append_pick(draft_id, team_id, player_id, "USER")
    _complete_if_finished(draft)
    return get_draft(draft_id, user_id)


def auto_simulate(draft_id: str, user_id: str) -> dict[str, Any]:
    """Auto-select available players until the controlled team is on the clock."""
    draft = _get_owned_draft(draft_id, user_id)
    picks = _DRAFT_PICKS[draft_id]
    while draft.status != "completed" and _current_team_id(len(picks)) != draft.controlled_team_id:
        available_player = _next_available_player(picks)
        if available_player is None:
            draft.status = "completed"
            break
        _append_pick(draft_id, _current_team_id(len(picks)), available_player, "AUTO")
    _complete_if_finished(draft)
    return get_draft(draft_id, user_id)


def _get_owned_draft(draft_id: str, user_id: str) -> DraftRun:
    """Return a draft only when it exists and belongs to the requesting user."""
    draft = _DRAFT_RUNS.get(draft_id)
    if draft is None:
        raise LookupError("Draft not found")
    if draft.user_id != user_id:
        raise PermissionError("Draft access denied")
    return draft


def _current_team_id(pick_count: int) -> str:
    """Return the team assigned to the next pick in the fixed draft order."""
    if pick_count >= len(_PLAYER_ORDER):
        return ""
    return _TEAM_ORDER[pick_count % len(_TEAM_ORDER)]


def _next_available_player(picks: list[DraftPick]) -> str | None:
    """Return the first player not already selected in the draft."""
    selected = {pick.player_id for pick in picks}
    return next((player for player in _PLAYER_ORDER if player not in selected), None)


def _append_pick(draft_id: str, team_id: str, player_id: str, source: str) -> None:
    """Append a validated pick to a draft's event sequence."""
    picks = _DRAFT_PICKS[draft_id]
    if player_id not in _PLAYER_ORDER:
        raise ValueError("Player does not exist")
    if any(pick.player_id == player_id for pick in picks):
        raise ValueError("Player has already been selected")
    pick_number = len(picks) + 1
    picks.append(
        DraftPick(
            id=f"pick-{draft_id}-{pick_number}",
            draft_run_id=draft_id,
            pick_number=pick_number,
            round_number=((pick_number - 1) // len(_TEAM_ORDER)) + 1,
            team_id=team_id,
            player_id=player_id,
            selection_source=source,
        )
    )


def _complete_if_finished(draft: DraftRun) -> None:
    """Mark a draft complete after all seeded player slots are selected."""
    if len(_DRAFT_PICKS[draft.id]) >= len(_PLAYER_ORDER):
        draft.status = "completed"
