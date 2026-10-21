"""Tests for the supplied 2027 NFL team-needs CSV import."""

from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.initialize import seed_reference_data
from app.db.models import TeamBoardRecord, TeamNeedRecord, UserRecord
from app.db.session import Base
from app.jobs.import_2027_team_needs import parse_team_needs_csv
from app.services.consensus_csv import read_consensus_csv
from app.services.prospect_board_import import import_board_snapshot
from app.services.prospect_pool import approve_projected_snapshot
from app.services.team_board_service import (
    copy_board_for_user,
    generate_persisted_team_board,
)


CSV_PATH = Path(__file__).resolve().parents[3] / "data" / "TeamNeeds" / "TeamNeeds_10212026.csv.csv"


def test_csv_import_normalizes_all_teams_and_position_aliases() -> None:
    needs = parse_team_needs_csv(CSV_PATH.read_text(encoding="utf-8"))

    assert len(needs) == 32 * 12
    by_key = {
        (need["team_id"], need["position_code"], need["role_level"]): need
        for need in needs
    }
    assert by_key[("team-7", "LB", "linebacker")]["need_score"] == 100
    assert by_key[("team-1", "QB", "quarterback")]["need_score"] == 100
    assert by_key[("team-28", "IOL", "offensive-guard")]["need_score"] == 80
    assert by_key[("team-28", "IOL", "offensive-center")]["need_score"] == 70
    assert by_key[("team-32", "EDGE", "edge")]["need_score"] == 70
    assert by_key[("team-8", "QB", "quarterback")]["need_score"] == 100


def test_csv_import_rejects_incomplete_duplicate_and_out_of_range_data() -> None:
    source = CSV_PATH.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="exactly"):
        parse_team_needs_csv(source.replace("TEAM,QB", "Team,QB", 1))
    with pytest.raises(ValueError, match="Duplicate team"):
        parse_team_needs_csv(source + "\n" + source.splitlines()[1] + "\n")
    with pytest.raises(ValueError, match="between 0 and 10"):
        parse_team_needs_csv(source.replace("Bengals,1,", "Bengals,11,", 1))


def test_import_preview_and_apply_regenerate_default_boards_without_touching_personal_boards(tmp_path) -> None:
    from app.jobs.import_2027_team_needs import import_2027_team_needs

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_reference_data(session)
        session.add(UserRecord(
            id="user-1", email="user@example.test", password_hash="test",
            first_name="Test", last_name="User",
        ))
        session.commit()
        prospects_path = tmp_path / "prospects.csv"
        prospects_path.write_text(
            "Rank,Player Name,Position,College\n"
            + "".join(f"{rank},Prospect {rank},WR,Alabama\n" for rank in range(1, 41)),
            encoding="utf-8",
        )
        snapshot = read_consensus_csv(
            prospects_path, draft_year=2027, snapshot_date=date(2026, 10, 20),
        )
        imported = import_board_snapshot(session, snapshot, commit=True)
        approve_projected_snapshot(session, imported["snapshot_id"])
        session.commit()

        default_board = generate_persisted_team_board(session, "team-1", 2027)
        personal_board = copy_board_for_user(session, default_board, "user-1")
        personal_order = [entry.player_id for entry in sorted(personal_board.entries, key=lambda entry: entry.rank_position)]
        session.add(TeamNeedRecord(
            team_id="team-1", draft_year=2027, position_code="QB", role_level="starter",
            need_score=90, quantity=1, source_name="Previous review", observed_at=datetime(2026, 10, 1),
        ))
        session.commit()

        source_csv = CSV_PATH.read_text(encoding="utf-8")
        preview = import_2027_team_needs(session, source_csv)
        assert preview["status"] == "dry_run"
        assert session.query(TeamNeedRecord).filter_by(is_active=True).count() == 1
        assert session.query(TeamBoardRecord).filter_by(board_type="default").count() == 1

        applied = import_2027_team_needs(session, source_csv, commit=True)
        assert applied["default_boards_generated"] == 32
        active_needs = session.query(TeamNeedRecord).filter_by(is_active=True).all()
        assert len(active_needs) == 32 * 12
        assert session.query(TeamNeedRecord).filter_by(is_active=False).count() == 1
        assert session.query(TeamBoardRecord).filter_by(board_type="default").count() == 33
        latest_default = session.query(TeamBoardRecord).filter_by(
            team_id="team-1", board_type="default",
        ).order_by(TeamBoardRecord.version.desc()).first()
        assert latest_default.scoring_version == "draft-score-v3-school-position"
        reloaded_personal = session.get(TeamBoardRecord, personal_board.id)
        assert [entry.player_id for entry in sorted(reloaded_personal.entries, key=lambda entry: entry.rank_position)] == personal_order
