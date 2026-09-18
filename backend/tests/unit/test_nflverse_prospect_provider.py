"""Tests for nflverse prospect normalization."""

from unittest.mock import Mock

from app.services.nflverse_prospect_provider import NflverseProspectProvider


def test_nflverse_combine_records_are_normalized() -> None:
    """Combine and player rows should produce the ingestion payload shape."""
    provider = Mock()
    provider.load_combine.return_value = [
        {"player_id": "n1", "pos": "OT", "height": 78, "weight": 315, "college_name": "Alabama"}
    ]
    provider.load_players.return_value = [{"id": "n1", "first_name": "Test", "last_name": "Tackle"}]

    records = NflverseProspectProvider(provider).fetch(2027)

    assert records == [{
        "id": "n1",
        "first_name": "Test",
        "last_name": "Tackle",
        "position": "OT",
        "college_id": "alabama",
        "college_name": "Alabama",
        "draft_year": 2027,
        "measurements": {
            "source_name": "nflverse-combine",
            "source_record_id": "n1",
            "height_inches": 78,
            "weight_lbs": 315,
            "raw_payload": {"player_id": "n1", "pos": "OT", "height": 78, "weight": 315, "college_name": "Alabama"},
        },
    }]


def test_nflverse_current_combine_schema_is_normalized() -> None:
    """Current nflverse combine fields should produce usable prospect records."""
    provider = Mock()
    provider.load_combine.return_value = [{"pfr_id": "AbcDe00", "player_name": "Jamie Example", "pos": "WR", "ht": "6-2", "school": "Alabama"}]
    provider.load_players.return_value = []

    record = NflverseProspectProvider(provider).fetch(2026)[0]

    assert record["id"] == "AbcDe00"
    assert record["first_name"] == "Jamie"
    assert record["last_name"] == "Example"
    assert record["measurements"]["height_inches"] == 74
