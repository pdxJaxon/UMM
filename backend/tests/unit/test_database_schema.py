"""Tests for the PostgreSQL-compatible relational schema."""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.db.initialize import seed_reference_data
from app.db.models import CollegeRecord, PlayerRecord, PositionImportanceRecord, TeamRecord
from app.db.session import Base


def test_database_schema_contains_core_tables() -> None:
    """The core draft entities should be represented as relational tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "users",
        "teams",
        "colleges",
        "position_importance",
        "team_needs",
        "team_drafting_tendencies",
        "team_prospect_meetings",
        "external_mock_picks",
        "prediction_evaluations",
        "prospect_refresh_runs",
        "team_boards",
        "team_board_entries",
        "players",
        "player_measurements",
        "player_athletic_scores",
        "player_derogatory_concerns",
        "draft_runs",
        "draft_picks",
        "draft_trades",
        "historical_draft_trades",
        "team_leadership",
    }


def test_reference_seed_is_idempotent() -> None:
    """Seeding twice should not create duplicate reference records."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_reference_data(session)
        seed_reference_data(session)
        assert session.query(TeamRecord).count() == 32
        assert session.query(CollegeRecord).count() == 136
        assert session.query(PositionImportanceRecord).count() == 15
        assert session.query(PlayerRecord).count() == 0


def test_seeded_teams_include_display_assets() -> None:
    """Every seeded NFL team should expose logo and official-site metadata."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_reference_data(session)
        teams = session.query(TeamRecord).all()

        assert len(teams) == 32
        assert all(team.logo_url.startswith("https://") for team in teams)
        assert all(team.official_url.startswith("https://www.nfl.com/") for team in teams)
