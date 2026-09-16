"""Tests for the maintained nflverse provider adapter."""

from unittest.mock import Mock

from app.services.nflverse_provider import NflverseProvider


def test_provider_delegates_historical_data_loads() -> None:
    """The adapter should delegate to nflreadpy with normalized season arguments."""
    loader = Mock()
    provider = NflverseProvider(loader)

    provider.load_combine([2024, 2025])
    provider.load_players()
    provider.load_draft_picks(range(2020, 2026))
    provider.load_rosters([2025])
    provider.load_depth_charts([2025])

    loader.load_combine.assert_called_once_with(seasons=[2024, 2025])
    loader.load_players.assert_called_once_with()
    loader.load_draft_picks.assert_called_once_with(seasons=[2020, 2021, 2022, 2023, 2024, 2025])
    loader.load_rosters.assert_called_once_with(seasons=[2025])
    loader.load_depth_charts.assert_called_once_with(seasons=[2025])