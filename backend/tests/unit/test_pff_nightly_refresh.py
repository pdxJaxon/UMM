"""Nightly refresh integration with isolated databases and deterministic collection."""

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.initialize import seed_reference_data
from app.db.models import (
    PlayerRecord, ProspectBoardRankingRecord, ProspectBoardSnapshotRecord,
    ProspectSourceIdentityRecord,
)
from app.db.session import Base
from app.services import pff_nightly_refresh as refresh
from app.services.pff_snapshot import PFFBoardSnapshot, load_identity_overrides


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_reference_data(db)
        yield db
    engine.dispose()


def board(day=0, count=2):
    return PFFBoardSnapshot.model_validate({
        "source_url": "https://www.pff.com/draft/big-board?season=2027",
        "draft_year": 2027,
        "collected_at": datetime(2026, 10, 14, tzinfo=UTC) + timedelta(days=day),
        "collection_method": "test DOM",
        "scope": "test board",
        "prospects": [
            {"overall_rank": rank, "name": f"Test Prospect {rank}", "position": "WR",
             "school": "Alabama", "pff_grade": None if rank == 1 else 0}
            for rank in range(1, count + 1)
        ],
    })


def run(session, tmp_path, **kwargs):
    return refresh.run_nightly_refresh(
        session, draft_year=2027, output_dir=tmp_path, min_prospects=1, **kwargs,
    )


def audits(tmp_path):
    return [json.loads(path.read_text()) for path in tmp_path.glob("*.run.json")]


def test_nightly_imports_preserve_history_and_identities(session, tmp_path, monkeypatch):
    snapshots = iter([board(), board(1)])
    monkeypatch.setattr(refresh, "collect_board", lambda *_args, **_kwargs: next(snapshots))
    first = run(session, tmp_path)
    second = run(session, tmp_path)
    assert first["status"] == second["status"] == "succeeded"
    assert first["import"]["new_players"] == 2
    assert second["import"]["existing_players"] == 2
    assert session.query(ProspectBoardSnapshotRecord).count() == 2
    assert session.query(ProspectBoardRankingRecord).count() == 4
    assert session.query(ProspectSourceIdentityRecord).count() == 2
    assert {player.eligibility_status for player in session.scalars(select(PlayerRecord))} == {"unconfirmed"}
    assert len(list(tmp_path.glob("*.snapshot.json"))) == 2
    for report in audits(tmp_path):
        assert report["status"] == "succeeded"
        assert report["completed_at"]
        snapshot = PFFBoardSnapshot.model_validate_json(Path(report["snapshot_path"]).read_text())
        assert len(snapshot.prospects) == 2
        assert snapshot.prospects[0].pff_grade is None
        assert snapshot.prospects[1].pff_grade == 0
    assert not list(tmp_path.glob("*.tmp"))


def test_same_snapshot_retry_does_not_duplicate_records(session, tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "collect_board", lambda *_args, **_kwargs: board())
    run(session, tmp_path)
    report = run(session, tmp_path)
    assert report["import"]["status"] == "already_imported"
    assert session.query(ProspectBoardSnapshotRecord).count() == 1
    assert session.query(PlayerRecord).count() == 2


def test_identity_conflict_archives_for_review_without_partial_import(session, tmp_path, monkeypatch, caplog):
    session.add(PlayerRecord(
        id="existing", first_name="Test", last_name="Prospect 2", college_id="ohio-state",
        position="WR", draft_year=2027, eligibility_status="confirmed",
    ))
    session.commit()
    monkeypatch.setattr(refresh, "collect_board", lambda *_args, **_kwargs: board())
    with pytest.raises(ValueError, match="School changed"):
        run(session, tmp_path)
    report = audits(tmp_path)[0]
    assert report["status"] == "failed"
    assert report["stage"] == "import"
    assert report["error_type"] == "ValueError"
    assert Path(report["snapshot_path"]).exists()
    assert "PFF refresh failed" in caplog.text
    assert session.query(PlayerRecord).count() == 1
    assert session.query(ProspectBoardSnapshotRecord).count() == 0
    assert session.query(ProspectSourceIdentityRecord).count() == 0
    reviewed = {board().prospects[1].key: "existing"}
    assert run(session, tmp_path, overrides=reviewed)["status"] == "succeeded"
    assert session.get(PlayerRecord, "existing").college_id == "ohio-state"


def test_count_drop_requires_manual_review(session, tmp_path, monkeypatch):
    snapshots = iter([board(), board(1, count=1)])
    monkeypatch.setattr(refresh, "collect_board", lambda *_args, **_kwargs: next(snapshots))
    run(session, tmp_path)
    with pytest.raises(ValueError, match="shrank from 2 to 1"):
        run(session, tmp_path)
    assert session.query(ProspectBoardSnapshotRecord).count() == 1
    assert len(list(tmp_path.glob("*.snapshot.json"))) == 2
    assert any(report["status"] == "failed" for report in audits(tmp_path))


def test_collection_failure_never_archives_partial_data(session, tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise TimeoutError("Rows did not render")

    monkeypatch.setattr(refresh, "collect_board", fail)
    with pytest.raises(TimeoutError):
        run(session, tmp_path)
    assert not list(tmp_path.glob("*.snapshot.json"))
    assert audits(tmp_path)[0]["stage"] == "collect"
    assert session.query(PlayerRecord).count() == 0
    # The failed run released the OS lock.
    monkeypatch.setattr(refresh, "collect_board", lambda *_args, **_kwargs: board())
    assert run(session, tmp_path)["status"] == "succeeded"


def test_overlapping_run_fails_before_collection(session, tmp_path, monkeypatch):
    def unexpected(*_args, **_kwargs):
        pytest.fail("Concurrent run must not collect or import")

    monkeypatch.setattr(refresh, "collect_board", unexpected)
    with refresh.refresh_lock(tmp_path / ".pff-refresh.lock"):
        with pytest.raises(OSError):
            run(session, tmp_path)
    assert audits(tmp_path)[0]["status"] == "failed"
    assert audits(tmp_path)[0]["stage"] == "lock"
    assert session.query(ProspectBoardSnapshotRecord).count() == 0


def test_lock_blocks_another_process_and_is_released_after_crash(tmp_path):
    script = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "from app.services.pff_nightly_refresh import refresh_lock\n"
        "try:\n"
        "    with refresh_lock(Path(sys.argv[1])):\n"
        "        os._exit(0)\n"
        "except OSError:\n"
        "    sys.exit(3)\n"
    )
    path = tmp_path / ".pff-refresh.lock"

    def child():
        return subprocess.run(
            [sys.executable, "-c", script, str(path)],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=20,
        )

    with refresh.refresh_lock(path):
        result = child()
        assert result.returncode == 3, result.stderr
    result = child()
    assert result.returncode == 0, result.stderr
    with refresh.refresh_lock(path):
        pass


def test_database_failure_rolls_back_every_record(session, tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "collect_board", lambda *_args, **_kwargs: board())

    def fail(_mapper, _connection, _target):
        raise ValueError("Simulated ranking write failure")

    event.listen(ProspectBoardRankingRecord, "before_insert", fail)
    try:
        with pytest.raises(ValueError, match="ranking write"):
            run(session, tmp_path)
    finally:
        event.remove(ProspectBoardRankingRecord, "before_insert", fail)
    session.rollback()
    assert session.query(PlayerRecord).count() == 0
    assert session.query(ProspectBoardSnapshotRecord).count() == 0
    assert audits(tmp_path)[0]["status"] == "failed"
    assert len(list(tmp_path.glob("*.snapshot.json"))) == 1


def test_batch_requests_reload_for_cdp_and_passes_count_floor(session, tmp_path, monkeypatch):
    from unittest.mock import Mock

    collect = Mock(return_value=board())
    monkeypatch.setattr(refresh, "collect_board", collect)
    run(session, tmp_path, cdp_url="http://127.0.0.1:9222")
    collect.assert_called_once_with(
        2027, 1, None, cdp_url="http://127.0.0.1:9222", refresh_existing=True,
    )


@pytest.mark.parametrize("options", [
    {"draft_year": 2019}, {"min_prospects": 0},
    {"storage_state": Path("session.json"), "cdp_url": "http://127.0.0.1:9222"},
])
def test_invalid_options_fail_before_artifact_or_database_writes(session, tmp_path, options):
    arguments = {"draft_year": 2027, "min_prospects": 1, **options}
    with pytest.raises(ValueError):
        refresh.run_nightly_refresh(session, output_dir=tmp_path, **arguments)
    assert list(tmp_path.iterdir()) == []
    assert session.query(PlayerRecord).count() == 0


def test_archive_failure_prevents_import(session, tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "collect_board", lambda *_args, **_kwargs: board())
    original = refresh._write_json

    def fail_archive(path, payload):
        if path.name.endswith(".snapshot.json"):
            raise OSError("Disk full")
        original(path, payload)

    monkeypatch.setattr(refresh, "_write_json", fail_archive)
    with pytest.raises(OSError, match="Disk full"):
        run(session, tmp_path)
    assert session.query(PlayerRecord).count() == 0
    assert audits(tmp_path)[0]["stage"] == "archive"


@pytest.mark.parametrize("payload", [[], {"key": 1}, {"key": ""}, None, "{invalid"])
def test_identity_map_rejects_invalid_shapes(tmp_path, payload):
    path = tmp_path / "map.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    with pytest.raises(ValueError):
        load_identity_overrides(path)


def test_cli_imports_and_reports_explicit_success(session, tmp_path, monkeypatch, capsys):
    from app.jobs import refresh_pff_board as job

    monkeypatch.setattr(job, "SessionLocal", lambda: Session(session.bind))
    monkeypatch.setattr(refresh, "collect_board", lambda *_args, **_kwargs: board())
    mapping = tmp_path / "mapping.json"
    mapping.write_text("{}", encoding="utf-8-sig")
    monkeypatch.setattr("sys.argv", [
        "refresh_pff_board", "--draft-year", "2027", "--min-prospects", "1",
        "--output-dir", str(tmp_path), "--identity-map", str(mapping),
    ])
    assert job.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "succeeded"
    assert session.query(PlayerRecord).count() == 2


def test_cli_bad_mapping_exits_nonzero_without_running(tmp_path, monkeypatch):
    from app.jobs import refresh_pff_board as job

    mapping = tmp_path / "mapping.json"
    mapping.write_text("[]")
    monkeypatch.setattr("sys.argv", [
        "refresh_pff_board", "--draft-year", "2027", "--output-dir", str(tmp_path),
        "--identity-map", str(mapping),
    ])
    with pytest.raises(SystemExit) as exc:
        job.main()
    assert exc.value.code == 2
    assert not list(tmp_path.glob("*.run.json"))


def test_cli_defaults_to_150_rows_and_passes_storage_state(tmp_path, monkeypatch, capsys):
    from unittest.mock import MagicMock, Mock
    from app.jobs import refresh_pff_board as job

    session_factory = MagicMock()
    monkeypatch.setattr(job, "SessionLocal", session_factory)
    batch = Mock(return_value={"status": "succeeded"})
    monkeypatch.setattr(job, "run_nightly_refresh", batch)
    storage = tmp_path / "session.json"
    monkeypatch.setattr("sys.argv", [
        "refresh_pff_board", "--draft-year", "2027", "--output-dir", str(tmp_path),
        "--storage-state", str(storage),
    ])
    assert job.main() == 0
    batch.assert_called_once_with(
        session_factory.return_value.__enter__.return_value,
        draft_year=2027, output_dir=tmp_path, min_prospects=150,
        storage_state=storage, cdp_url=None, overrides=None,
    )
    assert json.loads(capsys.readouterr().out)["status"] == "succeeded"
