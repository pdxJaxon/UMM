"""Synthetic pick ownership snapshots and frozen first-round integration."""

from datetime import UTC, datetime, timedelta
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.initialize import seed_reference_data
from app.db.models import DraftOrderSnapshotRecord, PlayerRecord, UserRecord
from app.db.session import Base
from app.services.draft_order_snapshots import DraftOrderSnapshot, approve_order, import_order, starting_order
from app.services.draft_repository import DraftRepository
from app.services.trade_engine import evaluate_trade


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_reference_data(db)
        db.add(UserRecord(id="order-user", email="order@example.com", password_hash="test",
                          first_name="Order", last_name="Test"))
        db.add_all([
            PlayerRecord(id=f"order-player-{i}", first_name="Test", last_name=str(i),
                         position="WR", college_id="alabama", draft_year=2027, eligibility_status="eligible")
            for i in range(40)
        ])
        db.commit()
        yield db
    engine.dispose()


def payload(day=0, owners=None):
    owners = owners or ["team-2", "team-1", "team-2"] + [f"team-{i}" for i in range(4, 33)]
    return {
        "draft_year": 2027, "collected_at": datetime(2026, 10, 14, tzinfo=UTC) + timedelta(days=day),
        "source_name": "synthetic", "source_url": "https://example.com/order",
        "order_status": "projected", "scope": "first_round", "expected_round_counts": [len(owners)],
        "picks": [
            {"overall_pick": i, "round_number": 1, "owner_team_id": owner,
             "original_team_id": None, "details": None}
            for i, owner in enumerate(owners, 1)
        ],
    }


def ingest(session, data=None, approve=False):
    result = import_order(session, DraftOrderSnapshot.model_validate(data or payload()), commit=True)
    if approve:
        approve_order(session, result["snapshot_id"], "Test Reviewer")
    return result["snapshot_id"]


def test_preview_idempotency_and_explicit_approval(session):
    snapshot = DraftOrderSnapshot.model_validate(payload())
    preview = import_order(session, snapshot)
    assert preview["status"] == "dry_run"
    assert session.query(DraftOrderSnapshotRecord).count() == 0
    identifier = ingest(session)
    assert import_order(session, snapshot, commit=True)["status"] == "already_imported"
    assert starting_order(session, 2027)[1]["kind"] == "reference_fallback"
    approve_order(session, identifier, "Reviewer")
    assert starting_order(session, 2027)[0][:3] == ["team-2", "team-1", "team-2"]
    approve_order(session, identifier, "Different Reviewer")
    assert session.get(DraftOrderSnapshotRecord, identifier).approved_by == "Reviewer"


def test_new_drafts_use_latest_collected_approved_order_and_freeze_old_drafts(session):
    repository = DraftRepository(session)
    older_id = ingest(session, approve=True)
    original = repository.create("order-user", "team-2", 2027, overall_randomness=0)
    session.commit()
    original_order = original.draft_order.copy()
    newer_id = ingest(session, payload(2, list(reversed(original_order))), approve=True)
    ingest(session, payload(1, ["team-1"] * 32), approve=True)
    ingest(session, payload(3, ["team-3"] * 32))
    newer = repository.create("order-user", "team-2", 2027)
    session.commit()
    assert original.draft_order == original_order
    assert original.order_provenance["snapshot_id"] == older_id
    assert newer.order_provenance["snapshot_id"] == newer_id
    assert newer.draft_order == list(reversed(original_order))
    assert starting_order(session, 2028)[1]["kind"] == "reference_fallback"


def test_repeated_owner_picks_auto_simulate_and_complete_with_absent_controlled_team(session):
    ingest(session, approve=True)
    repository = DraftRepository(session)
    draft = repository.create("order-user", "team-3", 2027, overall_randomness=0)
    session.commit()
    repository.auto_simulate(draft)
    session.commit()
    state = repository.state(draft)
    assert len(state["picks"]) == 32
    assert state["draft_run"]["status"] == "completed"
    assert [row["team_id"] for row in state["picks"]][:3] == ["team-2", "team-1", "team-2"]
    assert state["draft_run"]["order_provenance"]["order_status"] == "projected"
    assert len({row["player_id"] for row in state["picks"]}) == 32
    assert all(row["round_number"] == 1 for row in state["picks"])


def test_controlled_team_can_pick_multiple_times(session):
    ingest(session, approve=True)
    repository = DraftRepository(session)
    draft = repository.create("order-user", "team-2", 2027, overall_randomness=0)
    session.commit()
    repository.auto_simulate(draft)
    assert repository.state(draft)["current_pick_number"] == 1
    repository.add_pick(draft, "team-2", "order-player-0", "USER")
    repository.auto_simulate(draft)
    assert repository.state(draft)["current_pick_number"] == 3
    repository.add_pick(draft, "team-2", "order-player-39", "USER")
    repository.auto_simulate(draft)
    assert draft.status == "completed"


def test_different_first_round_size_and_later_rounds_are_not_simulated(session):
    data = payload(owners=["team-1"] * 31)
    data["scope"] = "full_draft"
    data["expected_round_counts"] = [31, 32, 34, 34, 34, 34, 34]
    for round_number, count in enumerate(data["expected_round_counts"][1:], 2):
        for _ in range(count):
            data["picks"].append({
                "overall_pick": len(data["picks"]) + 1, "round_number": round_number, "owner_team_id": "team-2",
            })
    ingest(session, data, approve=True)
    draft = DraftRepository(session).create("order-user", "team-1", 2027)
    assert len(draft.draft_order) == 31


@pytest.mark.parametrize("change", [
    {"draft_year": 2019}, {"collected_at": "2026-10-14"},
    {"source_url": "http://example.com"}, {"source_url": "https://user:password@example.com"},
    {"order_status": "official"}, {"expected_round_counts": [31]},
    {"expected_round_counts": [True]}, {"scope": "full_draft"},
])
def test_invalid_metadata_is_rejected(change):
    with pytest.raises(ValidationError):
        DraftOrderSnapshot.model_validate({**payload(), **change})


@pytest.mark.parametrize("change", [
    {"overall_pick": 2}, {"round_number": 2}, {"overall_pick": True},
])
def test_invalid_pick_order_is_rejected(change):
    data = payload()
    data["picks"][0].update(change)
    with pytest.raises(ValidationError):
        DraftOrderSnapshot.model_validate(data)


def test_unknown_teams_block_entire_import(session):
    for field in ("owner_team_id", "original_team_id"):
        data = payload()
        data["picks"][0][field] = "unknown-team"
        with pytest.raises(ValueError, match="Unknown team"):
            import_order(session, DraftOrderSnapshot.model_validate(data), commit=True)
    assert session.query(DraftOrderSnapshotRecord).count() == 0


def test_approval_requires_existing_snapshot_and_reviewer(session):
    with pytest.raises(ValueError, match="not found"):
        approve_order(session, "missing", "Reviewer")
    identifier = ingest(session)
    for reviewer in (" ", "x" * 151):
        with pytest.raises(ValueError, match="reviewer"):
            approve_order(session, identifier, reviewer)


def test_self_trades_are_not_created_for_repeated_owners():
    signals = {"team-1": [
        {"tendency_type": kind, "preference_score": 100, "confidence_score": 100}
        for kind in ("trade_up", "trade_down")
    ]}
    assert evaluate_trade(["team-1", "team-1"], 0, signals) is None


def test_trade_targets_exact_pick_when_owner_has_multiple_later_picks(session, monkeypatch):
    from app.services import draft_repository
    from app.services.trade_engine import TradeProposal

    ingest(session, payload(owners=["team-1", "team-2", "team-3", "team-2"]), approve=True)
    repository = DraftRepository(session)
    draft = repository.create("order-user", "team-1", 2027)
    frozen_order = draft.order_provenance["starting_order"].copy()
    proposal = TradeProposal(
        moving_down_team_id="team-1", moving_up_team_id="team-2",
        current_pick_number=1, acquired_pick_number=4, current_pick_value=100,
        acquired_pick_value=50, value_delta=50, evidence={},
    )
    monkeypatch.setattr(draft_repository, "evaluate_trade", lambda *_args: proposal)
    repository._maybe_execute_trade(draft, 0)
    assert draft.draft_order == ["team-2", "team-2", "team-3", "team-1"]
    assert draft.order_provenance["starting_order"] == frozen_order


def test_first_round_cannot_have_more_than_32_picks():
    with pytest.raises(ValidationError, match="cannot exceed"):
        DraftOrderSnapshot.model_validate(payload(owners=["team-1"] * 33))


def test_sqlite_initializer_adds_provenance_to_legacy_runs_without_overwriting_order(monkeypatch):
    from sqlalchemy import inspect, text
    from app.db import initialize

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE draft_runs (id VARCHAR(64) PRIMARY KEY, draft_order JSON NOT NULL)"))
        connection.execute(text("""INSERT INTO draft_runs VALUES ('legacy', '["team-2","team-1"]')"""))
    monkeypatch.setattr(initialize, "engine", engine)
    initialize.initialize_schema()
    initialize.initialize_schema()
    with engine.connect() as connection:
        assert "order_provenance" in {column["name"] for column in inspect(connection).get_columns("draft_runs")}
        row = connection.execute(text("SELECT draft_order, order_provenance FROM draft_runs")).one()
        assert json.loads(row[0]) == ["team-2", "team-1"]
        assert json.loads(row[1]) == {}
    engine.dispose()


def test_cli_preview_commit_and_approval(session, tmp_path, monkeypatch, capsys):
    from app.jobs import draft_order

    path = tmp_path / "order.json"
    data = payload()
    data["collected_at"] = data["collected_at"].isoformat()
    path.write_text(json.dumps(data), encoding="utf-8-sig")
    monkeypatch.setattr(draft_order, "SessionLocal", lambda: Session(session.bind))
    command = ["draft_order", "import", "--snapshot", str(path)]
    monkeypatch.setattr("sys.argv", command)
    assert draft_order.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    monkeypatch.setattr("sys.argv", [*command, "--commit"])
    assert draft_order.main() == 0
    identifier = json.loads(capsys.readouterr().out)["snapshot_id"]
    monkeypatch.setattr("sys.argv", [
        "draft_order", "approve", "--snapshot-id", identifier, "--reviewer", "Reviewer",
    ])
    assert draft_order.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "approved"
