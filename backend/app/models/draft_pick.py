"""Draft pick model for completed selections."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DraftPick:
    """Represents one player selection within a draft run."""

    id: str
    draft_run_id: str
    pick_number: int
    round_number: int
    team_id: str
    player_id: str
    selection_source: str
    selected_at: datetime = field(default_factory=datetime.utcnow)
