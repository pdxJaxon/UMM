"""Tests for the PostgreSQL-compatible relational schema."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db import initialize as database_initialize
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
        "prospect_source_identities",
        "prospect_board_snapshots",
        "prospect_board_rankings",
    }


def test_reference_seed_is_idempotent() -> None:
    """Seeding twice should not create duplicate reference records."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_reference_data(session)
        seed_reference_data(session)
        assert session.query(TeamRecord).count() == 32
        assert session.query(CollegeRecord).count() == 137
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


def test_initialize_schema_upgrades_previous_sqlite_schema(monkeypatch) -> None:
    """Existing SQLite records survive upgrades for newly added draft columns."""
    engine = create_engine("sqlite:///:memory:")
    legacy_schema = (
        """
        CREATE TABLE users (
            id VARCHAR(64) PRIMARY KEY, email VARCHAR(320) NOT NULL, password_hash VARCHAR(256) NOT NULL,
            first_name VARCHAR(100) NOT NULL, last_name VARCHAR(100) NOT NULL, is_active BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE teams (
            id VARCHAR(64) PRIMARY KEY, name VARCHAR(100) NOT NULL, city VARCHAR(100) NOT NULL,
            abbreviation VARCHAR(10) NOT NULL, draft_order INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE prospect_source_identities (
            id INTEGER PRIMARY KEY, source_name VARCHAR(100) NOT NULL, source_key VARCHAR(160) NOT NULL,
            player_id VARCHAR(64) NOT NULL, source_record_id VARCHAR(150)
        )
        """,
        """
        CREATE TABLE team_drafting_tendencies (
            id INTEGER PRIMARY KEY, team_id VARCHAR(64) NOT NULL, draft_year INTEGER,
            tendency_type VARCHAR(40) NOT NULL, position_code VARCHAR(20), metric_name VARCHAR(60),
            target_value VARCHAR(150), minimum_value NUMERIC(8, 2), maximum_value NUMERIC(8, 2),
            preference_score NUMERIC(5, 2) NOT NULL, confidence_score NUMERIC(5, 2) NOT NULL,
            sample_size INTEGER NOT NULL, source_name VARCHAR(100) NOT NULL, source_url VARCHAR(500),
            rationale VARCHAR(500), observed_at DATETIME NOT NULL, is_active BOOLEAN NOT NULL,
            raw_payload JSON NOT NULL
        )
        """,
        """
        CREATE TABLE historical_draft_trades (
            id INTEGER PRIMARY KEY, draft_year INTEGER NOT NULL, pick_number INTEGER NOT NULL,
            moving_up_team_id VARCHAR(64) NOT NULL, moving_down_team_id VARCHAR(64) NOT NULL,
            source_name VARCHAR(100) NOT NULL, source_url VARCHAR(500), observed_at DATETIME NOT NULL,
            raw_payload JSON NOT NULL
        )
        """,
        """
        CREATE TABLE draft_runs (
            id VARCHAR(64) PRIMARY KEY, user_id VARCHAR(64) NOT NULL, controlled_team_id VARCHAR(64) NOT NULL,
            draft_year INTEGER NOT NULL, status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL, completed_at DATETIME
        )
        """,
        """
        CREATE TABLE draft_picks (
            id VARCHAR(64) PRIMARY KEY, draft_run_id VARCHAR(64) NOT NULL, pick_number INTEGER NOT NULL,
            round_number INTEGER NOT NULL, team_id VARCHAR(64) NOT NULL, player_id VARCHAR(64) NOT NULL,
            selection_source VARCHAR(30) NOT NULL, selected_at DATETIME NOT NULL
        )
        """,
    )
    with engine.begin() as connection:
        for statement in legacy_schema:
            connection.execute(text(statement))
        connection.execute(
            text("INSERT INTO teams (id, name, city, abbreviation, draft_order) VALUES ('team-1', 'Cardinals', 'Arizona', 'ARI', 1)")
        )
        connection.execute(
            text(
                "INSERT INTO team_drafting_tendencies "
                "(id, team_id, tendency_type, preference_score, confidence_score, sample_size, source_name, "
                "observed_at, is_active, raw_payload) "
                "VALUES (1, 'team-1', 'position', 60, 80, 3, 'test', CURRENT_TIMESTAMP, 1, '{}')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO draft_runs "
                "(id, user_id, controlled_team_id, draft_year, status, created_at, updated_at) "
                "VALUES ('run-1', 'user-1', 'team-1', 2027, 'drafting', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO draft_picks "
                "(id, draft_run_id, pick_number, round_number, team_id, player_id, selection_source, selected_at) "
                "VALUES ('pick-1', 'run-1', 1, 1, 'team-1', 'player-1', 'manual', CURRENT_TIMESTAMP)"
            )
        )
    monkeypatch.setattr(database_initialize, "engine", engine)

    database_initialize.initialize_schema()
    database_initialize.initialize_schema()

    with engine.connect() as connection:
        assert connection.execute(text("SELECT name FROM teams WHERE id = 'team-1'")).scalar_one() == "Cardinals"
        assert connection.execute(
            text("SELECT tendency_type FROM team_drafting_tendencies WHERE id = 1")
        ).scalar_one() == "position"
        assert connection.execute(
            text(
                "SELECT overall_randomness, randomness_overrides, draft_order "
                "FROM draft_runs WHERE id = 'run-1'"
            )
        ).one() == (50, "{}", "[]")
        assert connection.execute(
            text(
                "SELECT randomness_factor, prediction_metadata "
                "FROM draft_picks WHERE id = 'pick-1'"
            )
        ).one() == (0, "{}")

    expected_columns = {
        "users": {"favorite_team_id"},
        "teams": {"randomness_score"},
        "team_drafting_tendencies": {"actor_type", "actor_id", "actor_name"},
        "historical_draft_trades": {
            "general_manager_id",
            "general_manager_name",
            "head_coach_id",
            "head_coach_name",
        },
        "draft_runs": {"randomness_overrides", "overall_randomness", "draft_order"},
        "draft_picks": {"randomness_factor", "prediction_metadata"},
        "prospect_source_identities": {"reviewed_name", "reviewed_school"},
    }
    inspector = inspect(engine)
    for table_name, expected in expected_columns.items():
        assert expected <= {column["name"] for column in inspector.get_columns(table_name)}
