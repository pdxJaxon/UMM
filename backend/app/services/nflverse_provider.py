"""Adapter for maintained nflverse data through ``nflreadpy``."""

from __future__ import annotations

from typing import Any


class NflverseProvider:
    """Load historical NFL data used to enrich prospect and team analysis."""

    def __init__(self, loader: Any | None = None) -> None:
        """Create a provider with an injectable loader module for tests."""
        if loader is None:
            try:
                import nflreadpy as loader_module
            except ImportError as exc:
                raise RuntimeError("Install nflreadpy to use the nflverse provider") from exc
            loader = loader_module
        self.loader = loader

    def load_combine(self, seasons: list[int] | range | None = None) -> Any:
        """Load historical NFL Combine measurements."""
        return self.loader.load_combine(seasons=list(seasons) if seasons is not None else None)

    def load_players(self) -> Any:
        """Load nflverse player identity and position mappings."""
        return self.loader.load_players()

    def load_draft_picks(self, seasons: list[int] | range | None = None) -> Any:
        """Load historical draft selections for tendency analysis."""
        return self.loader.load_draft_picks(seasons=list(seasons) if seasons is not None else None)

    def load_rosters(self, seasons: list[int] | range | None = None) -> Any:
        """Load historical roster data for team and player context."""
        return self.loader.load_rosters(seasons=list(seasons) if seasons is not None else None)

    def load_depth_charts(self, seasons: list[int] | range | None = None) -> Any:
        """Load depth charts for current team-need analysis."""
        return self.loader.load_depth_charts(seasons=list(seasons) if seasons is not None else None)