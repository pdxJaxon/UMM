"""Source snapshot, identity, mapping, and atomic import regression tests."""

from datetime import UTC, datetime
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.initialize import seed_reference_data
from app.db.models import (
    PlayerAthleticScoreRecord, PlayerRecord, ProspectBoardRankingRecord,
    ProspectBoardSnapshotRecord, ProspectSourceIdentityRecord,
)
from app.db.session import Base
from app.services.pff_browser_collector import snapshot_from_rendered
from app.services.pff_snapshot import PFFBoardSnapshot, canonical_school, source_key
from app.services.prospect_board_import import import_board_snapshot, resolve_identities


def _payload() -> dict:
    return {
        "source": "pff-big-board",
        "source_url": "https://www.pff.com/draft/big-board?season=2027",
        "draft_year": 2027,
        "collected_at": "2026-10-14T20:22:57Z",
        "source_updated_at_display": "Oct 6, 2026 11:59 am EDT",
        "collection_method": "rendered browser DOM; main board rows only",
        "scope": "All rendered rows; full draft class completeness not established",
        "prospects": [
            {"overall_rank": 1, "name": "Test Runner Jr.", "position": "HB", "school": "Alabama", "pff_grade": 87.5},
            {"overall_rank": 2, "name": "Test Lineman", "position": "DI", "school": "Ohio State", "pff_grade": None},
        ],
    }


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_reference_data(db)
        yield db
    engine.dispose()


@pytest.mark.parametrize(("source_position", "expected"), [
    ("HB", "RB"), ("DI", "DT"), ("ED", "EDGE"), ("T", "OT"), ("G", "IOL"), ("C", "IOL"),
])
def test_position_mappings_preserve_source_labels(session, source_position, expected):
    payload = _payload()
    payload["prospects"][0]["position"] = source_position
    snapshot = PFFBoardSnapshot.model_validate(payload)
    report = import_board_snapshot(session, snapshot, commit=True)
    session.commit()
    row = session.scalar(select(ProspectBoardRankingRecord).where(ProspectBoardRankingRecord.overall_rank == 1))
    assert row.source_position == source_position
    assert row.canonical_position == expected
    assert report["new_players"] == 2
    assert session.query(PlayerAthleticScoreRecord).count() == 0


@pytest.mark.parametrize(("label", "expected"), [
    ("Ohio State", "ohio-state"), ("Miami (FL)", "miami"),
    ("Miami (OH)", "miami-ohio"), ("Mississippi", "ole-miss"),
    ("Youngstown State", "youngstown-state"),
])
def test_school_resolution_is_explicit(label, expected):
    assert canonical_school(label) == expected


@pytest.mark.parametrize("change", [
    {"draft_year": 2026}, {"collected_at": "2026-10-14"},
    {"source_url": "https://example.com/draft/big-board?season=2027"},
    {"source": "unknown"}, {"prospects": []},
])
def test_invalid_snapshot_metadata_is_rejected(change):
    with pytest.raises(ValidationError):
        PFFBoardSnapshot.model_validate({**_payload(), **change})


@pytest.mark.parametrize(("field", "value"), [
    ("position", "NEW"), ("school", "Unreviewed School"),
    ("overall_rank", 3), ("overall_rank", True),
    ("pff_grade", -1), ("pff_grade", 101), ("pff_grade", float("nan")),
    ("pff_grade", True), ("name", "Single"),
])
def test_invalid_row_never_enters_the_importer(field, value):
    payload = _payload()
    payload["prospects"][0][field] = value
    with pytest.raises(ValidationError):
        PFFBoardSnapshot.model_validate(payload)


def test_duplicate_ranks_and_source_identities_are_rejected():
    for key, value in [("overall_rank", 1), ("source_record_id", "pff-duplicate")]:
        payload = _payload()
        if key == "source_record_id":
            payload["prospects"][0][key] = value
        payload["prospects"][1][key] = value
        with pytest.raises(ValidationError):
            PFFBoardSnapshot.model_validate(payload)


def test_rendered_heading_must_match_requested_year():
    payload = _payload()
    extracted = {"title": "BIG BOARD 2026", "prospects": payload["prospects"]}
    with pytest.raises(ValueError, match="heading"):
        snapshot_from_rendered(extracted, 2027)
    extracted["title"] = "BIG BOARD 2027"
    snapshot = snapshot_from_rendered(extracted, 2027, datetime(2026, 10, 14, tzinfo=UTC))
    assert snapshot.prospects[1].pff_grade is None


def test_dry_run_does_not_write_and_has_repeatable_ids(session):
    snapshot = PFFBoardSnapshot.model_validate(_payload())
    first = import_board_snapshot(session, snapshot)
    second = import_board_snapshot(session, snapshot)
    assert first == second
    assert first["status"] == "dry_run"
    assert first["missing_grades"] == 1
    assert session.query(PlayerRecord).count() == 0
    assert session.query(ProspectBoardSnapshotRecord).count() == 0
    assert session.query(ProspectSourceIdentityRecord).count() == 0


def test_import_is_idempotent_and_new_dates_preserve_history(session):
    payload = _payload()
    first_snapshot = PFFBoardSnapshot.model_validate(payload)
    first = import_board_snapshot(session, first_snapshot, commit=True)
    session.commit()
    assert import_board_snapshot(session, first_snapshot, commit=True)["status"] == "already_imported"
    payload["collected_at"] = "2026-10-21T20:22:57Z"
    payload["prospects"][0]["overall_rank"] = 2
    payload["prospects"][1]["overall_rank"] = 1
    payload["prospects"][1]["pff_grade"] = 90
    later = import_board_snapshot(session, PFFBoardSnapshot.model_validate(payload), commit=True)
    session.commit()
    assert first["snapshot_id"] != later["snapshot_id"]
    assert later["new_players"] == 0
    assert session.query(PlayerRecord).count() == 2
    assert session.query(ProspectSourceIdentityRecord).count() == 2
    assert session.query(ProspectBoardRankingRecord).count() == 4
    initial = session.scalars(select(ProspectBoardRankingRecord).where(
        ProspectBoardRankingRecord.snapshot_id == first["snapshot_id"],
    ).order_by(ProspectBoardRankingRecord.overall_rank)).all()
    assert initial[0].pff_grade == 87.5
    assert initial[1].pff_grade is None
    assert all(player.eligibility_status == "unconfirmed" for player in session.query(PlayerRecord))
    assert session.query(PlayerRecord).filter_by(first_name="Test", last_name="Runner Jr.").count() == 1


def _existing(session, player_id="existing", college_id="alabama", draft_year=2027):
    player = PlayerRecord(
        id=player_id, first_name="Test", last_name="Runner Jr.", position="RB",
        college_id=college_id, draft_year=draft_year, eligibility_status="eligible",
    )
    session.add(player)
    session.commit()
    return player


def test_exact_name_school_match_reuses_existing_player_without_overwriting(session):
    existing = _existing(session)
    snapshot = PFFBoardSnapshot.model_validate(_payload())
    report = import_board_snapshot(session, snapshot, commit=True)
    session.commit()
    assert report["existing_players"] == 1
    assert existing.eligibility_status == "eligible"
    assert session.scalar(select(ProspectSourceIdentityRecord).where(
        ProspectSourceIdentityRecord.source_key == snapshot.prospects[0].key,
    )).player_id == existing.id


def test_transfer_requires_reviewed_override_and_retains_profile(session):
    existing = _existing(session, college_id="texas")
    snapshot = PFFBoardSnapshot.model_validate(_payload())
    with pytest.raises(ValueError, match="School changed"):
        import_board_snapshot(session, snapshot, commit=True)
    assert session.query(ProspectBoardSnapshotRecord).count() == 0
    assert session.query(PlayerRecord).count() == 1
    import_board_snapshot(session, snapshot, {snapshot.prospects[0].key: existing.id}, commit=True)
    session.commit()
    assert existing.college_id == "texas"
    alias = session.scalar(select(ProspectSourceIdentityRecord).where(
        ProspectSourceIdentityRecord.source_key == snapshot.prospects[0].key,
    ))
    assert alias.player_id == existing.id


def test_ambiguous_names_are_never_silently_merged(session):
    _existing(session, "existing-1")
    _existing(session, "existing-2")
    snapshot = PFFBoardSnapshot.model_validate(_payload())
    with pytest.raises(ValueError, match="Ambiguous"):
        resolve_identities(session, snapshot)
    decisions = resolve_identities(session, snapshot, {snapshot.prospects[0].key: "existing-2"})
    assert decisions[0].player_id == "existing-2"


def test_conflicting_year_or_identity_overrides_fail_closed(session):
    _existing(session, draft_year=2026)
    snapshot = PFFBoardSnapshot.model_validate(_payload())
    with pytest.raises(ValueError, match="Draft-year conflict"):
        resolve_identities(session, snapshot)
    with pytest.raises(ValueError, match="keys not present"):
        resolve_identities(session, snapshot, {"typo": "existing"})
    with pytest.raises(ValueError, match="missing player"):
        resolve_identities(session, snapshot, {snapshot.prospects[0].key: "missing"})


def test_persistent_mapping_cannot_be_silently_reassigned(session):
    snapshot = PFFBoardSnapshot.model_validate(_payload())
    report = import_board_snapshot(session, snapshot, commit=True)
    session.commit()
    player_id = report["identities"][1]["player_id"]
    with pytest.raises(ValueError, match="conflicts"):
        resolve_identities(session, snapshot, {snapshot.prospects[0].key: player_id})


def test_keys_are_stable_without_rank_and_preserve_suffixes():
    assert source_key(" Test Runner Jr. ", "Alabama") == source_key("test runner jr.", "ALABAMA")
    assert source_key("Test Runner", "Alabama") != source_key("Test Runner Jr.", "Alabama")
    assert source_key("Old Name", "Alabama", "123") == source_key("New Name", "Texas", "123")


def test_failed_write_rolls_back_the_whole_snapshot(session):
    snapshot = PFFBoardSnapshot.model_validate(_payload())

    @event.listens_for(ProspectBoardRankingRecord, "before_insert")
    def fail_insert(_mapper, _connection, _target):
        raise ValueError("simulated write failure")

    try:
        with pytest.raises(ValueError, match="simulated"):
            import_board_snapshot(session, snapshot, commit=True)
    finally:
        event.remove(ProspectBoardRankingRecord, "before_insert", fail_insert)
    session.commit()
    assert session.query(PlayerRecord).count() == 0
    assert session.query(ProspectSourceIdentityRecord).count() == 0
    assert session.query(ProspectBoardSnapshotRecord).count() == 0


def test_cli_defaults_to_dry_run_and_requires_commit(session, tmp_path, monkeypatch, capsys):
    from app.db import session as session_module
    from app.jobs.pff_big_board import main

    snapshot_file = tmp_path / "board.json"
    snapshot_file.write_text(json.dumps(_payload()), encoding="utf-8")
    monkeypatch.setattr(session_module, "SessionLocal", lambda: Session(session.bind))
    command = ["pff_big_board", "import", "--snapshot", str(snapshot_file)]
    monkeypatch.setattr("sys.argv", command)
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    assert session.query(PlayerRecord).count() == 0
    monkeypatch.setattr("sys.argv", [*command, "--commit"])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "imported"
    assert session.query(PlayerRecord).count() == 2


def test_cli_collect_saves_a_snapshot_without_overwriting(tmp_path, monkeypatch, capsys):
    from app.jobs import pff_big_board

    snapshot = PFFBoardSnapshot.model_validate(_payload())
    output = tmp_path / "board.json"
    monkeypatch.setattr(pff_big_board, "collect_board", lambda *_args: snapshot)
    monkeypatch.setattr("sys.argv", [
        "pff_big_board", "collect", "--draft-year", "2027", "--output", str(output),
    ])
    assert pff_big_board.main() == 0
    assert json.loads(capsys.readouterr().out)["prospect_count"] == 2
    assert PFFBoardSnapshot.model_validate_json(output.read_text()).content_hash() == snapshot.content_hash()
    with pytest.raises(SystemExit) as error:
        pff_big_board.main()
    assert error.value.code == 2
