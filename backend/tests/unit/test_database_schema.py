"""Tests for the PostgreSQL-compatible relational schema."""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.db.initialize import seed_reference_data
from app.db.models import PlayerRecord, TeamRecord
from app.db.session import Base


def test_database_schema_contains_core_tables() -> None:
    """The core draft entities should be represented as relational tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "users",
        "teams",
        "players",
        "draft_runs",
        "draft_picks",
    }


def test_reference_seed_is_idempotent() -> None:
    """Seeding twice should not create duplicate reference records."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_reference_data(session)
        seed_reference_data(session)
        assert session.query(TeamRecord).count() == 3
        assert session.query(PlayerRecord).count() == 5
