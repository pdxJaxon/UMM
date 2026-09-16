"""Database initialization and local seed helpers."""

from sqlalchemy.orm import Session

from app.db.models import PlayerRecord, TeamRecord
from app.db.session import Base, SessionLocal, engine


TEAMS = (
    {"id": "team-1", "name": "Team One", "city": "Mock City", "abbreviation": "TMO", "draft_order": 1},
    {"id": "team-2", "name": "Team Two", "city": "Mock City", "abbreviation": "TMT", "draft_order": 2},
    {"id": "team-3", "name": "Team Three", "city": "Mock City", "abbreviation": "TMH", "draft_order": 3},
)

PLAYERS = tuple(
    {
        "id": f"player-{index}",
        "first_name": "Prospect",
        "last_name": str(index),
        "position": "ATH",
        "college_id": "college-1",
        "draft_year": 2026,
    }
    for index in range(1, 6)
)


def initialize_schema() -> None:
    """Create all configured tables in the active database."""
    Base.metadata.create_all(bind=engine)


def seed_reference_data(session: Session) -> None:
    """Insert idempotent team and prospect records for local development."""
    for team_data in TEAMS:
        if session.get(TeamRecord, team_data["id"]) is None:
            session.add(TeamRecord(**team_data))
    for player_data in PLAYERS:
        if session.get(PlayerRecord, player_data["id"]) is None:
            session.add(PlayerRecord(**player_data))
    session.commit()


def initialize_and_seed() -> None:
    """Create the schema and insert the reference records."""
    initialize_schema()
    session = SessionLocal()
    try:
        seed_reference_data(session)
    finally:
        session.close()


if __name__ == "__main__":
    initialize_and_seed()
