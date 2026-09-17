"""Database initialization and reference-data seed helpers."""

from sqlalchemy.orm import Session

from app.db.college_seed import COLLEGES
from app.db.models import CollegeRecord, PlayerRecord, PositionImportanceRecord, TeamRecord
from app.db.position_seed import POSITION_IMPORTANCE
from app.db.session import Base, SessionLocal, engine


def _team(
    number: int,
    city: str,
    name: str,
    abbreviation: str,
    draft_order: int,
    official_slug: str,
    randomness_score: float = 50,
) -> dict[str, object]:
    """Build a normalized NFL team seed record with display asset URLs."""
    abbreviation_lower = abbreviation.lower()
    return {
        "id": f"team-{number}",
        "name": name,
        "city": city,
        "abbreviation": abbreviation,
        "draft_order": draft_order,
        "logo_url": f"https://a.espncdn.com/i/teamlogos/nfl/500/{abbreviation_lower}.png",
        "helmet_url": None,
        "official_url": f"https://www.nfl.com/teams/{official_slug}/",
        "randomness_score": randomness_score,
    }


TEAMS = tuple(
    _team(*values)
    for values in (
        (1, "Arizona", "Cardinals", "ARI", 1, "arizona-cardinals"),
        (2, "Atlanta", "Falcons", "ATL", 2, "atlanta-falcons"),
        (3, "Baltimore", "Ravens", "BAL", 3, "baltimore-ravens"),
        (4, "Buffalo", "Bills", "BUF", 4, "buffalo-bills"),
        (5, "Carolina", "Panthers", "CAR", 5, "carolina-panthers"),
        (6, "Chicago", "Bears", "CHI", 6, "chicago-bears"),
        (7, "Cincinnati", "Bengals", "CIN", 7, "cincinnati-bengals"),
        (8, "Cleveland", "Browns", "CLE", 8, "cleveland-browns", 85),
        (9, "Dallas", "Cowboys", "DAL", 9, "dallas-cowboys"),
        (10, "Denver", "Broncos", "DEN", 10, "denver-broncos"),
        (11, "Detroit", "Lions", "DET", 11, "detroit-lions"),
        (12, "Green Bay", "Packers", "GB", 12, "green-bay-packers"),
        (13, "Houston", "Texans", "HOU", 13, "houston-texans"),
        (14, "Indianapolis", "Colts", "IND", 14, "indianapolis-colts"),
        (15, "Jacksonville", "Jaguars", "JAX", 15, "jacksonville-jaguars"),
        (16, "Kansas City", "Chiefs", "KC", 16, "kansas-city-chiefs"),
        (17, "Las Vegas", "Raiders", "LV", 17, "las-vegas-raiders"),
        (18, "Los Angeles", "Chargers", "LAC", 18, "los-angeles-chargers"),
        (19, "Los Angeles", "Rams", "LAR", 19, "los-angeles-rams"),
        (20, "Miami", "Dolphins", "MIA", 20, "miami-dolphins"),
        (21, "Minnesota", "Vikings", "MIN", 21, "minnesota-vikings"),
        (22, "New England", "Patriots", "NE", 22, "new-england-patriots"),
        (23, "New Orleans", "Saints", "NO", 23, "new-orleans-saints"),
        (24, "New York", "Giants", "NYG", 24, "new-york-giants"),
        (25, "New York", "Jets", "NYJ", 25, "new-york-jets"),
        (26, "Philadelphia", "Eagles", "PHI", 26, "philadelphia-eagles"),
        (27, "Pittsburgh", "Steelers", "PIT", 27, "pittsburgh-steelers"),
        (28, "San Francisco", "49ers", "SF", 28, "san-francisco-49ers"),
        (29, "Seattle", "Seahawks", "SEA", 29, "seattle-seahawks"),
        (30, "Tampa Bay", "Buccaneers", "TB", 30, "tampa-bay-buccaneers"),
        (31, "Tennessee", "Titans", "TEN", 31, "tennessee-titans"),
        (32, "Washington", "Commanders", "WSH", 32, "washington-commanders"),
    )
)

PLAYERS = tuple(
    {
        "id": f"player-{index}",
        "first_name": "Prospect",
        "last_name": str(index),
        "position": "ATH",
        "college_id": "alabama",
        "draft_year": 2027,
    }
    for index in range(1, 6)
)


def initialize_schema() -> None:
    """Create all configured tables in the active database."""
    Base.metadata.create_all(bind=engine)


def seed_reference_data(session: Session) -> None:
    """Insert idempotent NFL, college, and prospect records for local development."""
    for team_data in TEAMS:
        existing_team = session.get(TeamRecord, team_data["id"])
        if existing_team is None:
            session.add(TeamRecord(**team_data))
        else:
            for field, value in team_data.items():
                setattr(existing_team, field, value)
    for player_data in PLAYERS:
        existing_player = session.get(PlayerRecord, player_data["id"])
        if existing_player is None:
            session.add(PlayerRecord(**player_data))
        else:
            for field, value in player_data.items():
                setattr(existing_player, field, value)
    for college_data in COLLEGES:
        if session.get(CollegeRecord, college_data["id"]) is None:
            session.add(CollegeRecord(**college_data))
    for position_data in POSITION_IMPORTANCE:
        existing_position = session.get(PositionImportanceRecord, position_data["position_code"])
        if existing_position is None:
            session.add(PositionImportanceRecord(**position_data))
        else:
            for field, value in position_data.items():
                setattr(existing_position, field, value)
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
