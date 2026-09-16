"""Tests for the permitted PFF endpoint adapter."""

from unittest.mock import Mock

import httpx
import pytest

from app.services.pff_provider import PFFProvider


def test_provider_fetches_and_normalizes_pff_records() -> None:
    """The adapter should map PFF fields into the ingestion contract."""
    response = Mock()
    response.json.return_value = {
        "players": [
            {
                "id": "pff-1",
                "first_name": "Test",
                "last_name": "Prospect",
                "position": "OT",
                "college_slug": "alabama",
                "height_inches": 78,
                "weight_lbs": 315,
                "pff_grade": 91.2,
            }
        ]
    }
    client = Mock()
    client.get.return_value = response
    provider = PFFProvider("https://approved.example/prospects", "local-token", client=client)

    records = provider.fetch(2027)

    client.get.assert_called_once_with(
        "https://approved.example/prospects",
        params={"draft_year": 2027},
        headers={"Accept": "application/json", "Authorization": "Bearer local-token"},
    )
    assert records[0]["college_id"] == "alabama"
    assert records[0]["measurements"]["height_inches"] == 78
    assert records[0]["athletic_scores"][0]["score"] == 91.2


def test_provider_requires_endpoint() -> None:
    """The adapter should fail closed when no approved endpoint is configured."""
    with pytest.raises(RuntimeError, match="PFF_DATA_URL"):
        PFFProvider(endpoint="").fetch(2027)


def test_provider_rejects_malformed_response() -> None:
    """Malformed provider records should not enter the prospect database."""
    response = Mock()
    response.json.return_value = [{"id": "missing-college"}]
    client = Mock()
    client.get.return_value = response

    with pytest.raises(ValueError, match="id and college_id"):
        PFFProvider("https://approved.example/prospects", client=client).fetch(2027)