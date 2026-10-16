"""CSV import regressions for stable identities and dependent custom boards."""

from datetime import date, datetime, UTC
import json

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.initialize import seed_reference_data
from app.db.models import (
    DraftPickRecord, DraftRunRecord, PlayerRecord, ProspectBoardRankingRecord,
    ProspectBoardSnapshotRecord, ProspectSourceIdentityRecord, TeamBoardEntryRecord,
    TeamBoardRecord, UserRecord,
)
from app.db.session import Base
from app.services.consensus_csv import read_consensus_csv
from app.services.pff_snapshot import PFFBoardSnapshot
from app.services.prospect_board_import import import_board_snapshot

HEADER = "Rank,Player Name,Position,College\n"
ROWS = "1,Test Runner Jr.,RB,Alabama\n2,Test Lineman,DL,Ohio State\n"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_reference_data(db)
        yield db
    engine.dispose()


def _snapshot(tmp_path, rows=ROWS, day=15, **kwargs):
    path = tmp_path / "consensus.csv"
    path.write_text(HEADER + rows, encoding="utf-8-sig")
    return read_consensus_csv(path, draft_year=2027, snapshot_date=date(2026, 10, day), **kwargs)


def test_csv_preview_and_repeat_import_preserve_source_labels(session, tmp_path):
    snapshot = _snapshot(tmp_path)
    preview = import_board_snapshot(session, snapshot)
    assert preview["new_players"] == 2
    assert session.query(PlayerRecord).count() == 0
    assert session.query(ProspectSourceIdentityRecord).count() == 0
    report = import_board_snapshot(session, snapshot, commit=True)
    assert report["identities"] == preview["identities"]
    assert import_board_snapshot(session, snapshot, commit=True)["status"] == "already_imported"
    assert session.query(PlayerRecord).count() == 2
    assert session.query(ProspectBoardSnapshotRecord).count() == 1
    lineman = session.scalar(select(ProspectBoardRankingRecord).where(
        ProspectBoardRankingRecord.overall_rank == 2,
    ))
    assert lineman.source_position == "DL"
    assert lineman.canonical_position == "DT"
    assert lineman.pff_grade is None
    assert all(player.eligibility_status == "unconfirmed" for player in session.query(PlayerRecord))


def test_updates_preserve_custom_boards_drafts_and_missing_prospects(session, tmp_path):
    first = import_board_snapshot(session, _snapshot(tmp_path), commit=True)
    runner_id, lineman_id = [entry["player_id"] for entry in first["identities"]]
    runner = session.get(PlayerRecord, runner_id)
    runner.eligibility_status = "eligible"
    session.add(UserRecord(
        id="user", email="test@example.com", password_hash="not-a-real-password",
        first_name="Test", last_name="User",
    ))
    session.commit()
    board = TeamBoardRecord(
        team_id="team-1", user_id="user", draft_year=2027, board_type="personal",
        version=3, generated_at=datetime(2026, 10, 15, tzinfo=UTC), scoring_version="test-v1",
    )
    session.add(board)
    session.flush()
    session.add_all([
        TeamBoardEntryRecord(board_id=board.id, player_id=lineman_id, rank_position=1, score=90, is_active=True),
        TeamBoardEntryRecord(board_id=board.id, player_id=runner_id, rank_position=2, score=80, is_active=False),
        DraftRunRecord(id="draft", user_id="user", controlled_team_id="team-1", draft_year=2027),
    ])
    session.flush()
    session.add(DraftPickRecord(
        id="pick", draft_run_id="draft", pick_number=1, round_number=1,
        team_id="team-1", player_id=runner_id, selection_source="USER",
    ))
    session.commit()
    before = [(entry.id, entry.player_id, entry.rank_position, entry.score, entry.is_active)
              for entry in session.scalars(select(TeamBoardEntryRecord).order_by(TeamBoardEntryRecord.id))]

    reordered = _snapshot(tmp_path, "2,Test Runner Jr.,RB,Alabama\n1,Test Lineman,DL,Ohio State\n", day=16)
    update = import_board_snapshot(session, reordered, commit=True)
    assert update["new_players"] == 0
    missing = import_board_snapshot(
        session, _snapshot(tmp_path, "1,Test Runner Jr.,WR,Alabama\n", day=17), commit=True,
    )
    assert missing["missing_from_previous_snapshot"] == [
        {"player_id": lineman_id, "name": "Test Lineman", "previous_rank": 1},
    ]
    session.expire_all()
    after = [(entry.id, entry.player_id, entry.rank_position, entry.score, entry.is_active)
             for entry in session.scalars(select(TeamBoardEntryRecord).order_by(TeamBoardEntryRecord.id))]
    assert before == after
    assert session.get(TeamBoardRecord, board.id).version == 3
    assert session.get(DraftPickRecord, "pick").player_id == runner_id
    assert session.get(PlayerRecord, lineman_id) is not None
    assert session.get(PlayerRecord, runner_id).position == "RB"
    assert session.get(PlayerRecord, runner_id).eligibility_status == "eligible"
    assert session.query(ProspectBoardSnapshotRecord).count() == 3
    assert session.query(ProspectBoardRankingRecord).count() == 5


def test_csv_reuses_player_already_imported_from_another_source(session, tmp_path):
    pff = PFFBoardSnapshot.model_validate({
        "source_url": "https://www.pff.com/draft/big-board?season=2027",
        "draft_year": 2027, "collected_at": "2026-10-14T00:00:00Z",
        "collection_method": "test", "scope": "test",
        "prospects": [{"overall_rank": 1, "name": "Test Runner Jr.", "position": "RB", "school": "Alabama"}],
    })
    first = import_board_snapshot(session, pff, commit=True)
    second = import_board_snapshot(session, _snapshot(tmp_path), commit=True)
    assert second["existing_players"] == 1
    assert first["identities"][0]["player_id"] == second["identities"][0]["player_id"]
    assert session.query(PlayerRecord).count() == 2
    aliases = session.scalars(select(ProspectSourceIdentityRecord).where(
        ProspectSourceIdentityRecord.player_id == first["identities"][0]["player_id"],
    )).all()
    assert {alias.source_name for alias in aliases} == {"pff-big-board", "consensus-big-board"}


@pytest.mark.parametrize("rows,message", [
    ("1,Test Runner,RB,Alabama\n1,Test Lineman,DL,Ohio State\n", "Ranks"),
    ("1,Test Runner,RB,Alabama\n3,Test Lineman,DL,Ohio State\n", "Ranks"),
    ("1,Test Runner,RB,Alabama\n2,Test Runner,RB,Alabama\n", "Duplicate"),
    ("1,Test Runner,RB,\n", "missing"),
    ("1,Test Runner,RB,Alabama,extra\n", "extra"),
    ("no,Test Runner,RB,Alabama\n", "invalid rank"),
    ("1,Test Runner,UNKNOWN,Alabama\n", "position"),
    ("1,Test Runner,RB,Unknown School\n", "school"),
    ("", "at least 1"),
])
def test_invalid_csv_is_rejected(tmp_path, rows, message):
    with pytest.raises(ValueError, match=message):
        _snapshot(tmp_path, rows)


def test_csv_requires_exact_headers(tmp_path):
    path = tmp_path / "wrong.csv"
    path.write_text("Rank,Name,Position,College\n1,Test Runner,RB,Alabama\n", encoding="utf-8")
    with pytest.raises(ValueError, match="headers"):
        read_consensus_csv(path, draft_year=2027, snapshot_date=date(2026, 10, 15))


def test_limit_validates_all_identities_but_only_maps_selected_schools(tmp_path):
    snapshot = _snapshot(tmp_path, "2,Other Prospect,RB,Unmapped School\n1,Test Runner,RB,Alabama\n", limit=1)
    assert len(snapshot.prospects) == 1
    assert snapshot.prospects[0].name == "Test Runner"
    with pytest.raises(ValueError, match="Duplicate"):
        _snapshot(tmp_path, "1,Test Runner,RB,Alabama\n2,Test Runner,RB,Alabama\n", limit=1)
    for limit in (0, -1, 3):
        with pytest.raises(ValueError):
            _snapshot(tmp_path, limit=limit)


def test_transfer_and_year_conflicts_require_review(session, tmp_path):
    first = _snapshot(tmp_path, "1,Test Runner Jr.,RB,Alabama\n")
    report = import_board_snapshot(session, first, commit=True)
    player_id = report["identities"][0]["player_id"]
    transfer = _snapshot(tmp_path, "1,Test Runner Jr.,RB,Texas\n", day=16)
    with pytest.raises(ValueError, match="School changed"):
        import_board_snapshot(session, transfer, commit=True)
    reviewed = import_board_snapshot(session, transfer, {transfer.prospects[0].key: player_id}, commit=True)
    assert reviewed["new_players"] == 0
    assert session.get(PlayerRecord, player_id).college_id == "alabama"
    later_year = transfer.model_copy(update={"draft_year": 2028})
    with pytest.raises(ValueError, match="Draft-year conflict"):
        import_board_snapshot(session, later_year, commit=True)


def test_csv_failed_write_is_atomic(session, tmp_path):
    snapshot = _snapshot(tmp_path)

    def fail_insert(_mapper, _connection, _target):
        raise ValueError("simulated write failure")

    event.listen(ProspectBoardRankingRecord, "before_insert", fail_insert)
    try:
        with pytest.raises(ValueError, match="simulated"):
            import_board_snapshot(session, snapshot, commit=True)
    finally:
        event.remove(ProspectBoardRankingRecord, "before_insert", fail_insert)
    session.commit()
    assert session.query(PlayerRecord).count() == 0
    assert session.query(ProspectBoardSnapshotRecord).count() == 0
    assert session.query(ProspectSourceIdentityRecord).count() == 0


def test_csv_cli_previews_then_commits(session, tmp_path, monkeypatch, capsys):
    from app.jobs import import_consensus_csv

    _snapshot(tmp_path)
    monkeypatch.setattr(import_consensus_csv, "SessionLocal", lambda: Session(session.bind))
    command = [
        "import_consensus_csv", "--csv", str(tmp_path / "consensus.csv"),
        "--draft-year", "2027", "--snapshot-date", "2026-10-15",
    ]
    monkeypatch.setattr("sys.argv", command)
    assert import_consensus_csv.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    assert session.query(PlayerRecord).count() == 0
    monkeypatch.setattr("sys.argv", [*command, "--commit"])
    assert import_consensus_csv.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "imported"
    assert session.query(PlayerRecord).count() == 2
