"""Tests for the PostgreSQL draft repository behavior."""

import pytest
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
    session.add_all([PlayerRecord(**{**player, "draft_year": 2026}) for player in PLAYERS])
    session.add_all(
        PlayerRecord(
            id=f"draft-class-{number:02d}",
            first_name="Draft",
            last_name=f"Prospect {number}",
            position="ATH",
            college_id="alabama",
            draft_year=2026,
        )
        for number in range(1, 28)
    )
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


@pytest.mark.parametrize(
    ("player_id", "draft_year", "eligibility_status", "message"),
    [
        ("wrong-year", 2027, "eligible", "draft year"),
        ("unconfirmed", 2026, "unconfirmed", "not eligible"),
    ],
)
def test_repository_rejects_ineligible_manual_picks(player_id, draft_year, eligibility_status, message) -> None:
    session = _session()
    session.add(PlayerRecord(
        id=player_id,
        first_name="Test",
        last_name="Prospect",
        position="QB",
        college_id="alabama",
        draft_year=draft_year,
        eligibility_status=eligibility_status,
    ))
    session.flush()
    repository = DraftRepository(session)
    draft = repository.create("user-1", "team-1", 2026)

    with pytest.raises(ValueError, match=message):
        repository.add_pick(draft, "team-1", player_id, "USER")


def test_auto_simulation_reuses_team_tendencies_across_trades_and_predictions() -> None:
    session = _session()
    class PredictionProvider:
        provider_name = "test-provider"
        model_name = "test-model"

        def complete(self, _prompt, _randomness):
            return {"selected_player_id": "draft-class-01", "confidence": 0.5}

    repository = DraftRepository(session, PredictionProvider())
    draft = repository.create("user-1", "team-2", 2026)
    calls = []

    def load_tendencies(team_id, _draft_year):
        calls.append(team_id)
        return []

    repository._team_tendencies = load_tendencies

    repository.auto_simulate(draft)

    assert len(calls) == len(set(calls))
    assert calls.count("team-1") == 1
