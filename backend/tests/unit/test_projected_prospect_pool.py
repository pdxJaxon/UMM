"""Approval, board scoring, and complete first-round projected-pool regressions."""

from datetime import date, datetime, UTC
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.initialize import seed_reference_data
from app.db.models import (
    DraftRunRecord, PlayerAthleticScoreRecord, PlayerRecord, ProspectBoardSnapshotRecord,
    TeamBoardEntryRecord, TeamBoardRecord, UserRecord,
)
from app.db.session import Base, get_db
from app.main import app
from app.services.consensus_csv import read_consensus_csv
from app.services.draft_repository import DraftRepository
from app.services.prospect_board_import import import_board_snapshot
from app.services.prospect_pool import approve_projected_snapshot, pool_filter
from app.services.team_board_service import (
    copy_board_for_user, generate_persisted_team_board, reorder_personal_board,
)


@pytest.fixture
def session(monkeypatch):
    from dataclasses import replace
    from app.services import draft_repository

    monkeypatch.setattr(draft_repository, "settings", replace(draft_repository.settings, llm_api_key=""))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_reference_data(db)
        db.add(UserRecord(
            id="user", email="pool@example.com", password_hash="not-a-real-password",
            first_name="Pool", last_name="Tester",
        ))
        db.commit()
        yield db
    engine.dispose()


def _import(session, tmp_path, *, day=15, prefix="Prospect", count=40):
    path = tmp_path / f"{prefix}-{day}.csv"
    path.write_text("Rank,Player Name,Position,College\n" + "".join(
        f"{rank},{prefix} Number{rank},WR,Alabama\n" for rank in range(1, count + 1)
    ), encoding="utf-8")
    snapshot = read_consensus_csv(path, draft_year=2027, snapshot_date=date(2026, 10, day))
    return import_board_snapshot(session, snapshot, commit=True)


def _ids(session, snapshot_id):
    return set(session.scalars(select(PlayerRecord.id).where(pool_filter(2027, snapshot_id))))


def test_pff_default_copy_reload_and_reorder_keep_real_pool_and_source_evidence(session, tmp_path):
    from app.services.pff_csv import read_pff_csv

    session.add(PlayerRecord(
        id="legacy-sample", first_name="Sample", last_name="Only", position="WR",
        college_id="alabama", draft_year=2027, eligibility_status="eligible",
    ))
    session.commit()
    path = tmp_path / "pff.csv"
    path.write_text("Rank,Player,Position,School,PFF Grade,Analysis\n" + "".join(
        f"{rank},Source Candidate{rank},WR,Ohio State,,\n" for rank in range(1, 41)
    ), encoding="utf-8")
    snapshot = read_pff_csv(path, draft_year=2027, snapshot_date=date(2026, 10, 19))
    imported = import_board_snapshot(session, snapshot, commit=True)
    approve_projected_snapshot(session, imported["snapshot_id"])
    session.commit()
    default = generate_persisted_team_board(session, "team-1", 2027)
    default_ids = [entry.player_id for entry in sorted(default.entries, key=lambda entry: entry.rank_position)]
    assert len(default_ids) == 40
    assert "legacy-sample" not in default_ids
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {create_access_token('user')}"}
        url = "/api/teams/team-1/board"
        response = client.post(f"{url}/copy?draft_year=2027", headers=headers)
        assert response.status_code == 200
        copied_id = response.json()["board_id"]
        personal = client.get(f"{url}?draft_year=2027&board_type=personal", headers=headers).json()
        assert [entry["player_id"] for entry in personal["entries"]] == default_ids
        assert all(entry["first_name"] == "Source" for entry in personal["entries"])
        assert all(entry["college_name"] == "Ohio State" for entry in personal["entries"])
        assert all(entry["source_name"] == "pff-big-board" for entry in personal["entries"])
        assert all(entry["is_projected"] for entry in personal["entries"])
        assert {entry["source_rank"] for entry in personal["entries"]} == set(range(1, 41))
        assert all(
            entry["score_breakdown"]["source_snapshot_id"] == imported["snapshot_id"]
            for entry in personal["entries"]
        )
        order = list(reversed(default_ids))
        assert client.put(
            f"{url}/{copied_id}/order", headers=headers, json={"player_ids": order},
        ).status_code == 200
        session.expire_all()
        reloaded = client.get(f"{url}?draft_year=2027&board_type=personal", headers=headers).json()
        assert [entry["player_id"] for entry in reloaded["entries"]] == order
        assert reloaded["entries"][0]["source_rank"] == 40
        unchanged = client.get(f"{url}?draft_year=2027").json()
        assert [entry["player_id"] for entry in unchanged["entries"]] == default_ids
        assert client.get(
            "/api/teams/team-2/board?draft_year=2027&board_type=personal", headers=headers,
        ).json()["board"] is None
    finally:
        app.dependency_overrides.clear()


def test_import_does_not_approve_and_approval_does_not_change_eligibility(session, tmp_path):
    report = _import(session, tmp_path)
    assert _ids(session, report["snapshot_id"]) == set()
    with pytest.raises(ValueError, match="At least 32"):
        DraftRepository(session).create("user", "team-32", 2027)
    snapshot = approve_projected_snapshot(session, report["snapshot_id"])
    approved_at = snapshot.projected_pool_approved_at
    session.commit()
    approve_projected_snapshot(session, snapshot.id)
    assert snapshot.projected_pool_approved_at == approved_at
    assert len(_ids(session, snapshot.id)) == 40
    assert {player.eligibility_status for player in session.scalars(select(PlayerRecord))} == {"unconfirmed"}
    assert _ids(session, None) == set()
    assert session.query(TeamBoardRecord).count() == 0
    with pytest.raises(ValueError, match="does not exist"):
        approve_projected_snapshot(session, "missing")


def test_drafts_pin_approved_snapshot_and_exclude_unapproved_or_withdrawn_players(session, tmp_path):
    first = _import(session, tmp_path)
    approve_projected_snapshot(session, first["snapshot_id"])
    session.commit()
    repository = DraftRepository(session)
    draft = repository.create(
        "user", "team-32", 2027,
        randomness_overrides={f"team-{number}": 0 for number in range(1, 33)},
        overall_randomness=0,
    )
    old_ids = {entry["player_id"] for entry in first["identities"]}
    newer = _import(session, tmp_path, day=16, prefix="Different")
    assert {player["player_id"] for player in repository.eligible_players(draft)} == old_ids
    approve_projected_snapshot(session, newer["snapshot_id"])
    session.commit()
    generate_persisted_team_board(session, "team-1", 2027)
    fresh = repository.create("user", "team-32", 2027)
    assert fresh.prospect_snapshot_id == newer["snapshot_id"]
    assert draft.prospect_snapshot_id == first["snapshot_id"]
    assert {player["player_id"] for player in repository.eligible_players(draft)} == old_ids
    with pytest.raises(ValueError, match="not eligible"):
        repository.add_pick(draft, "team-1", newer["identities"][0]["player_id"], "USER")
    withdrawn = session.get(PlayerRecord, first["identities"][0]["player_id"])
    withdrawn.eligibility_status = "withdrawn"
    session.flush()
    with pytest.raises(ValueError, match="not eligible"):
        repository.add_pick(draft, "team-1", withdrawn.id, "USER")
    repository.auto_simulate(draft)
    pinned_picks = repository.state(draft)["picks"]
    assert len(pinned_picks) == 31
    assert pinned_picks[0]["player_id"] == first["identities"][1]["player_id"]
    assert {pick["player_id"] for pick in pinned_picks} <= old_ids
    old_draft = DraftRunRecord(id="legacy", user_id="user", controlled_team_id="team-1", draft_year=2027)
    session.add(old_draft)
    session.flush()
    assert repository.eligible_players(old_draft) == []


def test_confirmed_players_outside_snapshot_remain_only_in_legacy_pool(session, tmp_path):
    report = _import(session, tmp_path)
    session.add(PlayerRecord(
        id="legacy-sample", first_name="Legacy", last_name="Sample", position="ATH",
        college_id="alabama", draft_year=2027, eligibility_status="eligible",
    ))
    session.commit()
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    assert "legacy-sample" not in _ids(session, report["snapshot_id"])
    assert _ids(session, None) == {"legacy-sample"}


def test_source_rank_scores_are_auditable_and_custom_boards_survive_refresh(session, tmp_path):
    first = _import(session, tmp_path)
    approve_projected_snapshot(session, first["snapshot_id"])
    session.commit()
    default = generate_persisted_team_board(session, "team-1", 2027)
    assert len(default.entries) == 40
    ranked = sorted(default.entries, key=lambda entry: entry.rank_position)
    assert ranked[0].player_id == first["identities"][0]["player_id"]
    assert ranked[-1].player_id == first["identities"][-1]["player_id"]
    assert ranked[0].score_breakdown["source_rank"] == 1
    assert ranked[0].score_breakdown["source_evaluation"] == 100.0
    assert ranked[0].score_breakdown["evaluation_basis"] == "source_rank_percentile"
    assert ranked[0].score_breakdown["player_evaluation"] == 100.0
    assert ranked[0].score != 1
    personal = copy_board_for_user(session, default, "user")
    order = [entry.player_id for entry in reversed(ranked)]
    reorder_personal_board(session, personal, order)
    before = [(entry.id, entry.player_id, entry.rank_position, entry.score) for entry in personal.entries]
    newer = _import(session, tmp_path, day=16, count=32)
    approve_projected_snapshot(session, newer["snapshot_id"])
    session.commit()
    generate_persisted_team_board(session, "team-1", 2027)
    session.expire_all()
    assert [(entry.id, entry.player_id, entry.rank_position, entry.score) for entry in personal.entries] == before
    assert session.get(PlayerRecord, order[0]) is not None
    assert len(newer["missing_from_previous_snapshot"]) == 8
    assert session.query(PlayerAthleticScoreRecord).count() == 0


def test_source_rank_fallback_does_not_replace_existing_evaluation_signals(session, tmp_path):
    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.add(PlayerAthleticScoreRecord(
        player_id=report["identities"][0]["player_id"], source_name="test",
        observed_at=datetime.now(UTC), metric_name="pff_grade", score=75, score_scale="100",
    ))
    session.commit()
    board = generate_persisted_team_board(session, "team-1", 2027)
    entry = next(entry for entry in board.entries if entry.player_id == report["identities"][0]["player_id"])
    assert entry.score_breakdown["evaluation_basis"] == "stored_signals"
    assert entry.score_breakdown["player_evaluation"] == 75
    assert entry.score_breakdown["source_evaluation"] == 100


def test_pool_exhaustion_does_not_report_a_successful_completed_round(session, tmp_path):
    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    repository = DraftRepository(session)
    draft = repository.create("user", "team-32", 2027)
    for player in session.scalars(select(PlayerRecord)):
        player.eligibility_status = "withdrawn"
    session.flush()
    with pytest.raises(ValueError, match="before the first round is complete"):
        repository.auto_simulate(draft)
    assert draft.status == "drafting"


def test_full_round_api_uses_approved_projected_players_and_rejects_duplicates(session, tmp_path):
    report = _import(session, tmp_path, count=150)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    stale = TeamBoardRecord(
        team_id="team-1", draft_year=2027, board_type="default", version=1,
        generated_at=datetime.now(UTC), scoring_version="stale",
    )
    session.add(stale)
    excluded = PlayerRecord(
        id="unreviewed", first_name="Not", last_name="Approved", position="QB",
        college_id="alabama", draft_year=2027, eligibility_status="unconfirmed",
    )
    session.add(excluded)
    session.flush()
    session.add(TeamBoardEntryRecord(board_id=stale.id, player_id=excluded.id, rank_position=1, score=100))
    session.commit()

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    headers = {"Authorization": f"Bearer {create_access_token('user')}"}
    try:
        with TestClient(app) as client:
            start = client.post("/api/drafts", json={
                "controlled_team_id": "team-32", "draft_year": 2027, "overall_randomness": 0,
                "randomness_overrides": {f"team-{number}": 0 for number in range(1, 33)},
            }, headers=headers)
            assert start.status_code == 201, start.text
            players = start.json()["eligible_players"]
            assert len(players) == 150
            assert all(player["is_projected"] for player in players)
            assert players[0]["source_rank"] == 1
            assert players[0]["college_logo_url"].endswith(".png")
            draft_id = start.json()["draft_run_id"]
            simulated = client.post(f"/api/drafts/{draft_id}/auto-simulate", headers=headers)
            assert simulated.status_code == 200, simulated.text
            state = simulated.json()
            assert len(state["picks"]) == 31
            assert state["picks"][0]["player_id"] == players[0]["player_id"]
            assert state["current_team_id"] == "team-32"
            assert state["draft_run"]["prospect_snapshot_id"] == report["snapshot_id"]
            duplicate = client.post(f"/api/drafts/{draft_id}/picks", json={
                "team_id": "team-32", "player_id": state["picks"][0]["player_id"],
            }, headers=headers)
            assert duplicate.status_code == 409
            rejected = client.post(f"/api/drafts/{draft_id}/prediction", json={
                "team_id": "team-32", "pick_number": 32, "candidates": [{"player_id": "unreviewed"}],
            }, headers=headers)
            assert rejected.status_code == 409
            picked = {pick["player_id"] for pick in state["picks"]}
            available = next(player["player_id"] for player in players if player["player_id"] not in picked)
            completed = client.post(f"/api/drafts/{draft_id}/picks", json={
                "team_id": "team-32", "player_id": available,
            }, headers=headers)
            assert completed.status_code == 201, completed.text
            result = completed.json()
            assert result["draft_run"]["status"] == "completed"
            assert len(result["picks"]) == len({pick["player_id"] for pick in result["picks"]}) == 32
    finally:
        app.dependency_overrides.clear()


def test_approval_cli_defaults_to_preview(session, tmp_path, monkeypatch, capsys):
    from app.jobs import approve_projected_pool

    report = _import(session, tmp_path)
    monkeypatch.setattr(approve_projected_pool, "SessionLocal", lambda: Session(session.bind))
    command = ["approve_projected_pool", "--snapshot-id", report["snapshot_id"]]
    monkeypatch.setattr("sys.argv", command)
    assert approve_projected_pool.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    assert session.get(ProspectBoardSnapshotRecord, report["snapshot_id"]).projected_pool_approved_at is None
    monkeypatch.setattr("sys.argv", [*command, "--commit"])
    assert approve_projected_pool.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "approved"
    session.expire_all()
    assert session.get(ProspectBoardSnapshotRecord, report["snapshot_id"]).projected_pool_approved_at is not None


@pytest.mark.parametrize("controlled_team", ["team-1", "team-32"])
def test_recommendation_is_advisory_and_uses_available_persisted_evidence(session, tmp_path, controlled_team):
    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    repository = DraftRepository(session)
    draft = repository.create(
        "user", controlled_team, 2027,
        randomness_overrides={f"team-{number}": 0 for number in range(1, 33)},
        overall_randomness=0,
    )
    repository.auto_simulate(draft)
    before = repository.state(draft)["picks"]

    class Provider:
        provider_name = "test"
        model_name = "test-model"

        def complete(self, prompt, randomness):
            payload = json.loads(prompt)
            candidates = payload["candidates"]
            picked = {pick["player_id"] for pick in before}
            assert not picked & {candidate["player_id"] for candidate in candidates}
            assert candidates[0]["source_rank"] is not None
            assert candidates[0]["rank"] == 1
            assert payload["draft"]["team_id"] == controlled_team
            return {
                "selected_player_id": candidates[0]["player_id"], "confidence": .8,
                "alternatives": (
                    [{"player_id": candidates[1]["player_id"], "score": .7}]
                    if len(candidates) > 1 else []
                ),
                "reasoning_factors": ["Highest available source rank"], "evidence": ["source_rank"],
            }

    repository.prediction_provider = Provider()
    suggestion = repository.recommend(draft)
    assert suggestion["pick_number"] == len(before) + 1
    assert suggestion["recommended"]["rank"] == 1
    assert all(
        alternative["player_id"] != suggestion["recommended"]["player_id"]
        for alternative in suggestion["alternatives"]
    )
    assert repository.state(draft)["picks"] == before
    assert draft.status == "drafting"
    user_pick = suggestion["alternatives"][0] if suggestion["alternatives"] else suggestion["recommended"]
    repository.add_pick(draft, controlled_team, user_pick["player_id"], "USER")
    repository.prediction_provider = None
    repository.auto_simulate(draft)
    completed = repository.state(draft)
    assert completed["draft_run"]["status"] == "completed"
    assert len({pick["player_id"] for pick in completed["picks"]}) == 32
    with pytest.raises(ValueError, match="on the clock"):
        repository.recommend(draft)


def test_recommendation_rejects_wrong_turn_unavailable_model_and_stale_player(session, tmp_path):
    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    repository = DraftRepository(session)
    draft = repository.create("user", "team-32", 2027)
    with pytest.raises(ValueError, match="on the clock"):
        repository.recommend(draft)
    repository.auto_simulate(draft)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        repository.recommend(draft)

    class Provider:
        provider_name = "test"
        model_name = "test-model"

        def complete(self, prompt, randomness):
            player_id = json.loads(prompt)["candidates"][0]["player_id"]
            session.get(PlayerRecord, player_id).eligibility_status = "withdrawn"
            session.flush()
            return {"selected_player_id": player_id, "confidence": .8}

    repository.prediction_provider = Provider()
    with pytest.raises(ValueError, match="availability changed"):
        repository.recommend(draft)
    assert len(repository.state(draft)["picks"]) == 31


def test_recommendation_endpoint_owns_draft_and_closes_provider_without_saving_picks(session, tmp_path, monkeypatch):
    from app.api import drafts

    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    repository = DraftRepository(session)
    draft = repository.create("user", "team-1", 2027)
    session.commit()
    closed = []

    class Provider:
        provider_name = "test"
        model_name = "test-model"

        def complete(self, prompt, randomness):
            return {"selected_player_id": json.loads(prompt)["candidates"][0]["player_id"], "confidence": .8}

        def close(self):
            closed.append(True)

    monkeypatch.setattr(drafts, "OpenAICompatiblePredictionProvider", Provider)
    app.dependency_overrides[get_db] = lambda: session
    headers = {"Authorization": f"Bearer {create_access_token('user')}"}
    try:
        with TestClient(app) as client:
            url = f"/api/drafts/{draft.id}/recommendation"
            assert client.post(url).status_code == 401
            result = client.post(url, headers=headers)
            assert result.status_code == 200, result.text
            assert result.json()["recommended"]["source_rank"] == 1
            assert repository.state(draft)["picks"] == []
            assert client.post("/api/drafts/missing/recommendation", headers=headers).status_code == 404
            draft.user_id = "someone-else"
            assert client.post(url, headers=headers).status_code == 403
            assert len(closed) == 3
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("alternative", [{"player_id": "missing"}, {"player_id": []}])
def test_recommendation_rejects_invalid_alternatives(session, tmp_path, alternative):
    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()

    class Provider:
        provider_name = "test"
        model_name = "test-model"

        def complete(self, prompt, randomness):
            return {
                "selected_player_id": json.loads(prompt)["candidates"][0]["player_id"],
                "confidence": .8, "alternatives": [alternative],
            }

    repository = DraftRepository(session, Provider())
    draft = repository.create("user", "team-1", 2027)
    with pytest.raises(ValueError, match="unavailable alternative"):
        repository.recommend(draft)


def _league_manifest(snapshot_id):
    from app.services.league_data_refresh import LeagueRefreshManifest

    source = {"name": "Synthetic test fixture", "url": "https://example.com/test-source", "observed_on": "2026-10-15"}
    order = [f"team-{number}" for number in range(32, 0, -1)]
    return LeagueRefreshManifest.model_validate({
        "draft_year": 2027, "reviewed_on": "2026-10-16", "reviewed_by": "Test reviewer",
        "prospect_snapshot_id": snapshot_id, "order_basis": "projected-one-pick-per-team",
        "order_source": source, "draft_order": order,
        "team_needs": [{
            "team_id": team_id, "source": source,
            "needs": [{"position_code": "WR", "role_level": "starter", "need_score": 80,
                       "quantity": 1, "rationale": "Synthetic test need, not a real roster assessment"}],
        } for team_id in order],
    })


def test_reviewed_league_refresh_is_previewed_atomic_idempotent_and_preserves_user_state(session, tmp_path, monkeypatch):
    from app.db.models import LeagueDataRefreshRecord, TeamNeedRecord, TeamRecord
    from app.services.league_data_refresh import import_league_refresh
    from app.services.draft_order import draft_order_for_year

    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    old_default = generate_persisted_team_board(session, "team-1", 2027)
    personal = copy_board_for_user(session, old_default, "user")
    before = [(entry.id, entry.player_id, entry.rank_position, entry.score) for entry in personal.entries]
    draft = DraftRepository(session).create("user", "team-1", 2027)
    old_order = list(draft.draft_order)
    session.add(TeamNeedRecord(
        team_id="team-1", draft_year=2027, position_code="QB", role_level="starter",
        need_score=90, quantity=1, source_name="Old assessment", observed_at=datetime(2026, 10, 1),
    ))
    session.commit()
    manifest = _league_manifest(report["snapshot_id"])
    preview = import_league_refresh(session, manifest)
    assert preview["status"] == "dry_run"
    assert session.query(LeagueDataRefreshRecord).count() == 0
    assert session.query(TeamBoardRecord).count() == 2
    assert session.query(TeamNeedRecord).filter_by(is_active=True).count() == 1
    applied = import_league_refresh(session, manifest, commit=True)
    assert applied["default_boards_generated"] == 32
    assert applied["full_refresh_date_unchanged"]
    assert session.query(LeagueDataRefreshRecord).count() == 1
    assert session.query(TeamNeedRecord).filter_by(is_active=True).count() == 32
    assert session.query(TeamNeedRecord).filter_by(is_active=False).count() == 1
    assert session.query(TeamBoardRecord).count() == 34
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = TestClient(app).get("/api/teams?draft_year=2027")
        assert response.status_code == 200
        assert [team["id"] for team in response.json()] == manifest.draft_order
        assert response.json()[0]["draft_order_basis"] == "projected-one-pick-per-team"
        assert response.json()[0]["draft_order_reviewed_on"] == "2026-10-16"
    finally:
        app.dependency_overrides.clear()
    assert [(entry.id, entry.player_id, entry.rank_position, entry.score) for entry in personal.entries] == before
    assert draft.draft_order == old_order
    fresh = DraftRepository(session).create("user", "team-1", 2027)
    assert fresh.draft_order == manifest.draft_order
    assert fresh.order_basis == "projected-one-pick-per-team"
    assert DraftRepository(session).state(draft)["draft_run"]["order_basis"] == "seeded-sample"
    assert draft_order_for_year(session, 2028) == old_order
    assert session.get(TeamRecord, "team-1").draft_order == 1
    assert import_league_refresh(session, manifest, commit=True)["status"] == "unchanged"
    assert session.query(TeamBoardRecord).count() == 34
    from app.services import team_board_service

    captured = []

    def capture_candidates(session, team_id, draft_year, candidates, **kwargs):
        captured.extend(candidates)

    monkeypatch.setattr(team_board_service, "generate_team_board", capture_candidates)
    generate_persisted_team_board(session, "team-1", 2027)
    assert captured
    assert {candidate["pick_number"] for candidate in captured} == {32}


@pytest.mark.parametrize("failure", ["duplicate-team", "unknown-position", "wrong-snapshot", "incomplete-teams"])
def test_reviewed_refresh_rejects_invalid_inputs_without_writes(session, tmp_path, failure):
    from app.db.models import LeagueDataRefreshRecord, TeamNeedRecord
    from app.services.league_data_refresh import LeagueRefreshManifest, import_league_refresh

    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    payload = _league_manifest(report["snapshot_id"]).model_dump(mode="json")
    if failure == "duplicate-team":
        payload["team_needs"][0]["team_id"] = payload["team_needs"][1]["team_id"]
    elif failure == "unknown-position":
        payload["team_needs"][0]["needs"][0]["position_code"] = "FAKE"
    elif failure == "wrong-snapshot":
        payload["prospect_snapshot_id"] = "unapproved"
    else:
        payload["draft_order"][0] = "unknown-team"
    with pytest.raises(ValueError):
        import_league_refresh(session, LeagueRefreshManifest.model_validate(payload), commit=True)
    assert session.query(LeagueDataRefreshRecord).count() == 0
    assert session.query(TeamNeedRecord).count() == 0
    assert session.query(TeamBoardRecord).count() == 0


def test_reviewed_refresh_rolls_back_all_needs_and_defaults_on_generation_failure(session, tmp_path, monkeypatch):
    from app.db.models import LeagueDataRefreshRecord, TeamNeedRecord
    from app.services import league_data_refresh

    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    manifest = _league_manifest(report["snapshot_id"])
    generate = league_data_refresh.generate_persisted_team_board
    calls = []

    def fail_second_board(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError("Injected generation failure")
        return generate(*args, **kwargs)

    monkeypatch.setattr(league_data_refresh, "generate_persisted_team_board", fail_second_board)
    with pytest.raises(RuntimeError, match="Injected"):
        league_data_refresh.import_league_refresh(session, manifest, commit=True)
    assert session.query(LeagueDataRefreshRecord).count() == 0
    assert session.query(TeamNeedRecord).count() == 0
    assert session.query(TeamBoardRecord).count() == 0


@pytest.mark.parametrize("field,value", [
    ("order_basis", "official"),
    ("reviewed_on", "2999-01-01"),
    ("reviewed_by", " "),
])
def test_reviewed_manifest_rejects_unreviewed_or_misleading_metadata(field, value):
    from app.services.league_data_refresh import LeagueRefreshManifest

    payload = _league_manifest("snapshot").model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValueError):
        LeagueRefreshManifest.model_validate(payload)


def test_league_refresh_cli_previews_without_mutation(session, tmp_path, monkeypatch, capsys):
    from app.jobs import import_league_refresh
    from app.db.models import LeagueDataRefreshRecord

    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    session.commit()
    manifest_path = tmp_path / "reviewed.json"
    manifest_path.write_text(_league_manifest(report["snapshot_id"]).model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(import_league_refresh, "SessionLocal", lambda: Session(session.bind))
    monkeypatch.setattr("sys.argv", ["import_league_refresh", "--manifest", str(manifest_path)])
    assert import_league_refresh.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    assert session.query(LeagueDataRefreshRecord).count() == 0
    monkeypatch.setattr("sys.argv", ["import_league_refresh", "--schema"])
    assert import_league_refresh.main() == 0
    assert "order_source" in json.loads(capsys.readouterr().out)["properties"]


@pytest.mark.parametrize("change", ["duplicate-role", "late-source", "invalid-score", "unknown-field"])
def test_league_refresh_rejects_invalid_evidence(session, tmp_path, change):
    from app.services.league_data_refresh import LeagueRefreshManifest, import_league_refresh

    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    payload = _league_manifest(report["snapshot_id"]).model_dump(mode="json")
    if change == "duplicate-role":
        payload["team_needs"][0]["needs"] *= 2
    elif change == "late-source":
        payload["order_source"]["observed_on"] = "2026-10-17"
    elif change == "invalid-score":
        payload["team_needs"][0]["needs"][0]["need_score"] = 101
    else:
        payload["official_order"] = True
    with pytest.raises(ValueError):
        import_league_refresh(session, LeagueRefreshManifest.model_validate(payload), commit=True)


def test_later_league_review_retains_history_and_rejects_stale_replay(session, tmp_path, monkeypatch):
    from app.db.models import LeagueDataRefreshRecord, TeamNeedRecord
    from app.services import league_data_refresh

    class ReviewDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 18, tzinfo=tz)

    monkeypatch.setattr(league_data_refresh, "datetime", ReviewDateTime)
    report = _import(session, tmp_path)
    approve_projected_snapshot(session, report["snapshot_id"])
    first = _league_manifest(report["snapshot_id"])
    league_data_refresh.import_league_refresh(session, first, commit=True)
    payload = first.model_dump(mode="json")
    payload["reviewed_on"] = "2026-10-17"
    payload["draft_order"] = list(reversed(payload["draft_order"]))
    payload["team_needs"][0]["needs"][0]["need_score"] = 70
    second = league_data_refresh.LeagueRefreshManifest.model_validate(payload)
    league_data_refresh.import_league_refresh(session, second, commit=True)
    assert session.query(LeagueDataRefreshRecord).count() == 2
    assert session.query(TeamNeedRecord).filter_by(draft_year=2027, is_active=True).count() == 32
    assert session.query(TeamNeedRecord).filter_by(source_name="Synthetic test fixture").count() == 64
    from app.services.draft_order import draft_order_for_year
    assert draft_order_for_year(session, 2027) == second.draft_order
    with pytest.raises(ValueError, match="later"):
        league_data_refresh.import_league_refresh(session, first, commit=True)
