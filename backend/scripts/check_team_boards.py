"""Ad-hoc verification script: generate persisted team boards for all teams
and report entry counts / errors. Run with:

    cd backend
    python scripts/check_team_boards.py
"""
from app.db.initialize import TEAMS, initialize_schema, seed_reference_data
from app.db.session import SessionLocal
from app.services.team_board_service import generate_persisted_team_board

DRAFT_YEAR = 2027


def main() -> None:
    initialize_schema()
    session = SessionLocal()
    try:
        seed_reference_data(session)
        for team in TEAMS:
            try:
                board = generate_persisted_team_board(session, team["id"], DRAFT_YEAR)
                print(team["id"], team["abbreviation"], len(board.entries))
            except Exception as exc:  # noqa: BLE001 - diagnostic script
                print("ERROR", team["id"], type(exc).__name__, exc)
    finally:
        session.close()


if __name__ == "__main__":
    main()
