"""Authorized PFF export parsing, safe updates, and nightly discovery regressions."""

from datetime import UTC, date, datetime
import json

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.initialize import seed_reference_data
from app.db.models import (
    PlayerRecord, ProspectBoardRankingRecord, ProspectBoardSnapshotRecord,
    ProspectSourceIdentityRecord, TeamBoardEntryRecord, TeamBoardRecord, UserRecord,
)
from app.db.session import Base
from app.services.pff_csv import import_pff_csv, newest_pff_csv, read_pff_csv
from app.services.consensus_csv import read_consensus_csv
from app.services.prospect_board_import import import_board_snapshot

HEADER = "Rank,Player,Position,School,PFF Grade,Analysis\n"
ROWS = '1,Test Runner,HB,Alabama,87.5,"Synthetic note, with comma"\n2,Test Lineman,DI,Ohio State,,\n'
DAY = date(2026, 10, 19)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_reference_data(db)
        yield db
    engine.dispose()


def export(tmp_path, rows=ROWS, day="2026-10-19"):
    path = tmp_path / f"pff-my-big-board-{day}.csv"
    path.write_text(HEADER + rows, encoding="utf-8-sig")
    return path


def ingest(session, path, day=DAY, **kwargs):
    return import_pff_csv(session, path, draft_year=2027, snapshot_date=day, min_prospects=2, **kwargs)


def test_export_maps_pff_grades_without_copying_analysis(tmp_path):
    snapshot = read_pff_csv(export(tmp_path), draft_year=2027, snapshot_date=DAY)
    assert snapshot.source == "pff-big-board"
    assert [row.pff_grade for row in snapshot.prospects] == [87.5, None]
    assert snapshot.position_map["HB"] == "RB"
    assert snapshot.position_map["DI"] == "DT"
    assert "Synthetic note" not in snapshot.model_dump_json()
    assert snapshot.collected_at == datetime(2026, 10, 19, tzinfo=UTC)
    assert snapshot.content_hash() == read_pff_csv(
        export(tmp_path), draft_year=2027, snapshot_date=DAY,
    ).content_hash()


@pytest.mark.parametrize("rows,message", [
    ("1,Test Runner,HB,Alabama,NaN,\n", "Invalid PFF candidate"),
    ("1,Test Runner,HB,Alabama,101,\n", "Invalid PFF candidate"),
    ("1,Test Runner,HB,Alabama,unavailable,\n", "Invalid PFF candidate"),
    ("1,Test Runner,HB,Alabama,,\n1,Test Lineman,DI,Ohio State,,\n", "Ranks"),
    ("1,Test Runner,HB,Alabama,,\n3,Test Lineman,DI,Ohio State,,\n", "Ranks"),
    ("1,Test Runner,HB,Alabama,,\n2,Test Runner,HB,Alabama,,\n", "Duplicate"),
    ("1,Test Runner,HB,Alabama,\n", "missing"),
    ("1,Test Runner,HB,Alabama,,,extra\n", "extra"),
    ("1,,HB,Alabama,,\n", "missing candidate"),
    ("one,Test Runner,HB,Alabama,,\n", "invalid rank"),
    ('1,Test Runner,HB,Alabama,,"unterminated\n', "Invalid PFF CSV"),
    ("1,Test Runner,ZZ,Alabama,,\n", "position"),
    ("1,Test Runner,HB,Unmapped,,\n", "school"),
    ("", "at least 1"),
])
def test_invalid_export_fails_before_writes(session, tmp_path, rows, message):
    with pytest.raises(ValueError, match=message):
        ingest(session, export(tmp_path, rows), commit=True)
    assert session.query(PlayerRecord).count() == 0
    assert session.query(ProspectBoardSnapshotRecord).count() == 0


def test_headers_and_minimum_guard_against_wrong_or_partial_files(session, tmp_path):
    path = export(tmp_path)
    with pytest.raises(ValueError, match="at least 150"):
        import_pff_csv(session, path, draft_year=2027, snapshot_date=DAY, commit=True)
    with pytest.raises(ValueError, match="positive"):
        import_pff_csv(session, path, draft_year=2027, snapshot_date=DAY, min_prospects=0)
    path.write_text(HEADER.replace("Player,", "Player Name,") + ROWS, encoding="utf-8")
    with pytest.raises(ValueError, match="headers"):
        ingest(session, path)


def test_discovery_uses_filename_not_modification_time_and_rejects_bad_inbox(tmp_path):
    old = export(tmp_path, day="2026-10-18")
    newest = export(tmp_path)
    old.touch()
    (tmp_path / "unrelated.csv").write_text("ignored", encoding="utf-8")
    assert newest_pff_csv(tmp_path) == (newest, DAY)
    bad = export(tmp_path, day="2026-02-30")
    with pytest.raises(ValueError, match="Invalid date"):
        newest_pff_csv(tmp_path)
    bad.unlink()
    future = export(tmp_path, day="2099-01-01")
    with pytest.raises(ValueError, match="Future"):
        newest_pff_csv(tmp_path)
    with pytest.raises(ValueError, match="future"):
        read_pff_csv(future, draft_year=2027, snapshot_date=date(2099, 1, 1))
    future.unlink()
    (tmp_path / "pff-my-big-board-invalid.csv").touch()
    with pytest.raises(ValueError, match="filename"):
        newest_pff_csv(tmp_path)


def test_missing_directory_and_empty_inbox_are_explicit(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        newest_pff_csv(tmp_path / "missing")
    with pytest.raises(ValueError, match="No pff"):
        newest_pff_csv(tmp_path)


def test_preview_commit_rerun_and_newer_rankings_preserve_profiles_and_personal_board(session, tmp_path):
    legacy = tmp_path / "legacy.csv"
    legacy.write_text("Rank,Player Name,Position,College\n1,Test Runner,RB,Alabama\n", encoding="utf-8")
    first = import_board_snapshot(session, read_consensus_csv(
        legacy, draft_year=2027, snapshot_date=date(2026, 10, 15),
    ), commit=True)
    player_id = first["identities"][0]["player_id"]
    session.get(PlayerRecord, player_id).eligibility_status = "eligible"
    session.add(UserRecord(id="user", email="pff@example.test", password_hash="test", first_name="A", last_name="B"))
    session.commit()
    board = TeamBoardRecord(
        team_id="team-1", user_id="user", draft_year=2027, board_type="personal",
        version=1, generated_at=datetime.now(UTC), scoring_version="test",
    )
    session.add(board)
    session.flush()
    session.add(TeamBoardEntryRecord(board_id=board.id, player_id=player_id, rank_position=1, score=80))
    session.commit()
    preview = ingest(session, export(tmp_path))
    assert preview["existing_players"] == 1
    assert preview["new_players"] == 1
    assert session.query(ProspectBoardSnapshotRecord).count() == 1
    report = ingest(session, export(tmp_path), commit=True)
    assert report["identities"][0]["player_id"] == player_id
    assert report["missing_grades"] == 1
    assert ingest(session, export(tmp_path), commit=True)["status"] == "already_imported"
    changed = ROWS.replace("87.5", "88.0")
    with pytest.raises(ValueError, match="correction manually"):
        ingest(session, export(tmp_path, changed), commit=True)
    ingest(session, export(tmp_path, changed, "2026-10-20"), date(2026, 10, 20), commit=True)
    assert ingest(session, export(tmp_path, changed), commit=True)["status"] == "skipped_older"
    assert session.query(PlayerRecord).count() == 2
    assert session.query(ProspectSourceIdentityRecord).count() == 3
    assert session.get(PlayerRecord, player_id).eligibility_status == "eligible"
    assert session.query(TeamBoardRecord).count() == 1
    assert session.query(TeamBoardEntryRecord).one().player_id == player_id
    assert session.query(TeamBoardEntryRecord).one().rank_position == 1
    assert all(row.projected_pool_approved_at is None for row in session.query(ProspectBoardSnapshotRecord))
    ranking = session.scalar(select(ProspectBoardRankingRecord).where(
        ProspectBoardRankingRecord.snapshot_id == report["snapshot_id"],
        ProspectBoardRankingRecord.overall_rank == 1,
    ))
    assert float(ranking.pff_grade) == 87.5
    assert ranking.source_position == "HB"


def test_reviewed_school_override_preserves_profile_and_records_source_school(session, tmp_path):
    initial = ingest(session, export(tmp_path), commit=True)
    player_id = initial["identities"][0]["player_id"]
    path = export(tmp_path, ROWS.replace("Alabama", "Texas"), "2026-10-20")
    day = date(2026, 10, 20)
    with pytest.raises(ValueError, match="School changed"):
        ingest(session, path, day, commit=True)
    row = read_pff_csv(path, draft_year=2027, snapshot_date=day).prospects[0]
    report = ingest(session, path, day, overrides={row.key: player_id}, commit=True)
    assert session.get(PlayerRecord, player_id).college_id == "alabama"
    assert report["new_players"] == 0
    ranking = session.scalar(select(ProspectBoardRankingRecord).where(
        ProspectBoardRankingRecord.snapshot_id == report["snapshot_id"],
        ProspectBoardRankingRecord.player_id == player_id,
    ))
    assert ranking.source_school == "Texas"


def test_cli_defaults_to_preview_and_requires_explicit_metadata(session, tmp_path, monkeypatch, capsys):
    from app.jobs import import_pff_csv as job

    export(tmp_path)
    monkeypatch.setattr(job, "SessionLocal", lambda: Session(session.bind))
    arguments = ["job", "--directory", str(tmp_path), "--draft-year", "2027", "--min-prospects", "2"]
    monkeypatch.setattr("sys.argv", arguments)
    assert job.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    assert session.query(PlayerRecord).count() == 0
    monkeypatch.setattr("sys.argv", [*arguments, "--commit"])
    assert job.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "imported"
    monkeypatch.setattr("sys.argv", [*arguments, "--snapshot-date", "2026-10-19"])
    with pytest.raises(SystemExit):
        job.main()
    monkeypatch.setattr("sys.argv", ["job", "--csv", str(export(tmp_path)), "--draft-year", "2027"])
    with pytest.raises(SystemExit):
        job.main()
