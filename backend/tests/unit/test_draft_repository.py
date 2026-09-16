"""Tests for the PostgreSQL draft repository behavior."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.initialize import PLAYERS, TEAMS
from app.db.models import PlayerRecord, TeamRecord, UserRecord
from app.db.session import Base
from app.services.draft_repository import DraftRepository


def _session() -> Session:
    """Create an isolated relational test session with reference data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(UserRecord(id="user-1", email="user@example.com", password_hash="hash", first_name="Test", last_name="User"))
    session.add_all([TeamRecord(**team) for team in TEAMS])
    session.add_all([PlayerRecord(**player) for player in PLAYERS])
    session.commit()
    return session


def test_repository_persists_draft_and_pick() -> None:
    """Draft creation and pick submission should survive session flushes."""
    session = _session()
    repository = DraftRepository(session)

    draft = repository.create("user-1", "team-1", 2026)
    repository.add_pick(draft, "team-1", "player-1", "USER")
    session.commit()

    state = repository.state(repository.get_owned(draft.id, "user-1"))
    assert state["current_pick_number"] == 2
    assert state["picks"][0]["player_id"] == "player-1"


def test_repository_enforces_owner_and_duplicate_rules() -> None:
    """Unauthorized reads and duplicate selections must be rejected."""
    session = _session()
    repository = DraftRepository(session)
    draft = repository.create("user-1", "team-1", 2026)
    repository.add_pick(draft, "team-1", "player-1", "USER")

    try:
        repository.get_owned(draft.id, "other-user")
        raise AssertionError("Expected ownership validation")
    except PermissionError:
        pass

    try:
        repository.add_pick(draft, "team-2", "player-1", "AUTO")
        raise AssertionError("Expected duplicate validation")
    except ValueError as error:
        assert str(error) == "Player has already been selected"
