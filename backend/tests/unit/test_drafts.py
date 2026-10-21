"""Contract-level tests for the mock draft lifecycle."""

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.initialize import PLAYERS, TEAMS
from app.db.models import DraftPickRecord, PlayerRecord, TeamBoardEntryRecord, TeamBoardRecord, TeamDraftingTendencyRecord, TeamNeedRecord, TeamRecord, UserRecord
from app.db.session import Base, get_db
from app.main import app
from app.services.draft_repository import DraftRepository


@pytest.fixture(autouse=True)
def isolate_draft_store() -> None:
    """Provide an isolated relational database before each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all(
        [
            UserRecord(
                id="user-1",
                email="user-1@example.com",
                password_hash="hash",
                first_name="Test",
                last_name="User",
            ),
            UserRecord(
                id="owner",
                email="owner@example.com",
                password_hash="hash",
                first_name="Draft",
                last_name="Owner",
            ),
        ]
    )
    session.add_all([TeamRecord(**team) for team in TEAMS])
    session.add_all([PlayerRecord(**{**player, "draft_year": 2026}) for player in PLAYERS])
    session.add_all(
        PlayerRecord(
            id=f"draft-class-{number:02d}",
            first_name="Draft",
            last_name=f"Prospect {number}",
            position="ATH",
            college_id="alabama",
            draft_year=2026,
        )
        for number in range(1, 28)
    )
    session.commit()

    def override_get_db():
        """Yield the isolated test session to FastAPI."""
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield session
    app.dependency_overrides.clear()
    session.close()


def test_controlled_team_flow_auto_simulates_other_teams() -> None:
    """The server should auto-pick team one before team two's user pick."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}

    response = client.post(
        "/api/drafts",
        json={
            "controlled_team_id": "team-2",
            "draft_year": 2026,
            "randomness_overrides": {"team-1": 0},
        },
        headers=headers,
    )
    assert response.status_code == 201
    draft_id = response.json()["draft_run_id"]

    response = client.post(f"/api/drafts/{draft_id}/auto-simulate", headers=headers)
    assert response.status_code == 200
    state = response.json()
    assert state["current_team_id"] == "team-2"
    assert state["picks"][0]["team_id"] == "team-1"
    assert state["picks"][0]["selection_source"] == "FALLBACK"

    response = client.post(
        f"/api/drafts/{draft_id}/picks",
        json={"team_id": "team-2", "player_id": "player-2"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["picks"][1]["selection_source"] == "USER"


def test_bounded_simulation_saves_one_pick_per_call_and_stops_for_user():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}
    created = client.post("/api/drafts", headers=headers, json={
        "controlled_team_id": "team-3", "draft_year": 2026,
    })
    draft_id = created.json()["draft_run_id"]
    url = f"/api/drafts/{draft_id}/auto-simulate?max_picks=1"
    for count in (1, 2):
        response = client.post(url, headers=headers)
        assert response.status_code == 200
        assert len(response.json()["picks"]) == count
        persisted = client.get(f"/api/drafts/{draft_id}", headers=headers)
        assert persisted.json()["picks"] == response.json()["picks"]
    state = client.post(url, headers=headers).json()
    assert len(state["picks"]) == 2
    assert state["current_team_id"] == "team-3"
    for invalid in (0, -1, 33):
        assert client.post(
            f"/api/drafts/{draft_id}/auto-simulate?max_picks={invalid}", headers=headers,
        ).status_code == 422
    assert len(client.get(f"/api/drafts/{draft_id}", headers=headers).json()["picks"]) == 2


def test_repository_rejects_nonpositive_pick_limit(isolate_draft_store):
    repository = DraftRepository(isolate_draft_store)
    draft = repository.create("user-1", "team-3", 2026)
    with pytest.raises(ValueError, match="positive"):
        repository.auto_simulate(draft, max_picks=0)


def test_single_pick_advancement_completes_round_without_duplicates():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}
    created = client.post("/api/drafts", headers=headers, json={
        "controlled_team_id": "team-1", "draft_year": 2026,
    }).json()
    draft_id = created["draft_run_id"]
    response = client.post(
        f"/api/drafts/{draft_id}/picks", headers=headers,
        json={"team_id": "team-1", "player_id": created["eligible_players"][0]["player_id"]},
    )
    assert response.status_code == 201
    for count in range(2, 33):
        response = client.post(f"/api/drafts/{draft_id}/auto-simulate?max_picks=1", headers=headers)
        assert response.status_code == 200
        assert len(response.json()["picks"]) == count
    state = response.json()
    assert state["draft_run"]["status"] == "completed"
    assert len({pick["player_id"] for pick in state["picks"]}) == 32
    assert client.post(
        f"/api/drafts/{draft_id}/auto-simulate?max_picks=1", headers=headers,
    ).json()["picks"] == state["picks"]


def test_draft_uses_seeded_team_order_and_all_persisted_prospects(isolate_draft_store: Session) -> None:
    """Draft order and valid picks should come from persisted league data, not fixtures."""
    repository = DraftRepository(isolate_draft_store)
    draft = repository.create("user-1", "team-8", 2026)
    expected_order = [team["id"] for team in sorted(TEAMS, key=lambda team: team["draft_order"])]

    assert draft.draft_order == expected_order
    assert repository.current_team_id(3, draft.draft_order) == "team-4"

    prospect = PlayerRecord(
        id="prospect-extra",
        first_name="Draft",
        last_name="Prospect",
        position="QB",
        college_id="alabama",
        draft_year=2026,
    )
    isolate_draft_store.add(prospect)
    isolate_draft_store.flush()
    repository.add_pick(draft, "team-1", prospect.id, "USER")
    assert repository.state(draft)["picks"][0]["player_id"] == prospect.id


def test_full_first_round_reaches_late_controlled_team_and_completes(isolate_draft_store: Session) -> None:
    """A full prospect pool should support user picks at late positions and finish round one."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}
    draft_id = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-32", "draft_year": 2026},
        headers=headers,
    ).json()["draft_run_id"]

    response = client.post(f"/api/drafts/{draft_id}/auto-simulate", headers=headers)

    assert response.status_code == 200
    state = response.json()
    assert state["current_team_id"] == "team-32"
    assert len(state["picks"]) == 31
    available_player = next(
        player.id
        for player in isolate_draft_store.query(PlayerRecord).all()
        if player.id not in {pick["player_id"] for pick in state["picks"]}
    )

    response = client.post(
        f"/api/drafts/{draft_id}/picks",
        json={"team_id": "team-32", "player_id": available_player},
        headers=headers,
    )

    assert response.status_code == 201
    state = response.json()
    assert state["draft_run"]["status"] == "completed"
    assert len(state["picks"]) == 32


def test_draft_requires_enough_eligible_prospects(isolate_draft_store: Session) -> None:
    """A draft must not silently complete before every first-round team can pick."""
    repository = DraftRepository(isolate_draft_store)

    with pytest.raises(ValueError, match="eligible prospects are required"):
        repository.create("user-1", "team-1", 2027)


def test_start_draft_returns_all_eligible_players_for_the_draft_year(isolate_draft_store: Session) -> None:
    """The UI draft pool should not be limited to the user's current team board."""
    isolate_draft_store.add_all([
        PlayerRecord(
            id="wrong-year",
            first_name="Wrong",
            last_name="Year",
            position="QB",
            college_id="alabama",
            draft_year=2027,
        ),
        PlayerRecord(
            id="ineligible",
            first_name="Ineligible",
            last_name="Prospect",
            position="QB",
            college_id="alabama",
            draft_year=2026,
            eligibility_status="unconfirmed",
        ),
    ])
    isolate_draft_store.commit()
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + create_access_token("user-1")}

    response = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-1", "draft_year": 2026},
        headers=headers,
    )

    assert response.status_code == 201
    eligible_players = response.json()["eligible_players"]
    assert len(eligible_players) == 32
    assert {player["player_id"] for player in eligible_players} == {
        player.id
        for player in isolate_draft_store.query(PlayerRecord).all()
        if player.draft_year == 2026 and player.eligibility_status == "eligible"
    }


def test_auto_simulation_executes_historic_trade_and_stops_for_controlled_team(isolate_draft_store: Session) -> None:
    """A strong trade-down and trade-up history should change the order before a pick."""
    observed_at = datetime.now(UTC)
    isolate_draft_store.add_all([
        TeamDraftingTendencyRecord(
            team_id="team-1", draft_year=None, tendency_type="trade_down",
            preference_score=100, confidence_score=100, sample_size=5,
            source_name="historical-drafts", rationale="Frequently accumulates extra picks",
            observed_at=observed_at,
        ),
        TeamDraftingTendencyRecord(
            team_id="team-2", draft_year=None, tendency_type="trade_up",
            preference_score=100, confidence_score=100, sample_size=4,
            source_name="historical-drafts", rationale="Frequently consolidates picks",
            observed_at=observed_at,
        ),
    ])
    isolate_draft_store.commit()

    repository = DraftRepository(isolate_draft_store)
    draft = repository.create("user-1", "team-2", 2026)
    repository.auto_simulate(draft)

    state = repository.state(draft)
    assert state["current_team_id"] == "team-2"
    assert state["picks"] == []
    assert state["draft_run"]["draft_order"][:3] == ["team-2", "team-1", "team-3"]
    assert len(state["draft_run"]["draft_order"]) == len(TEAMS)
    assert len(state["trades"]) == 1
    assert state["trades"][0]["moving_up_team_id"] == "team-2"
    assert state["trades"][0]["moving_down_team_id"] == "team-1"
    assert state["trades"][0]["value_delta"] > 0


def test_draft_state_reports_overall_randomness_setting() -> None:
    """A draft run should preserve the user's global randomness baseline."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}

    response = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-1", "draft_year": 2026, "overall_randomness": 25},
        headers=headers,
    )

    assert response.status_code == 201
    state = client.get(f"/api/drafts/{response.json()['draft_run_id']}", headers=headers)
    assert state.json()["draft_run"]["overall_randomness"] == 25


def test_draft_rejects_out_of_range_overall_randomness() -> None:
    """Global randomness must remain within the documented 0-100 range."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}

    response = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-1", "draft_year": 2026, "overall_randomness": 101},
        headers=headers,
    )

    assert response.status_code == 422


def test_prediction_endpoint_requires_configured_llm(isolate_draft_store: Session, monkeypatch) -> None:
    """The prediction endpoint must fail explicitly when no model key is configured."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}
    draft_id = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-2", "draft_year": 2026, "overall_randomness": 25},
        headers=headers,
    ).json()["draft_run_id"]

    class MissingProvider:
        def __init__(self):
            raise RuntimeError("LLM_API_KEY is not configured")

    monkeypatch.setattr("app.api.drafts.OpenAICompatiblePredictionProvider", MissingProvider)

    response = client.post(
        f"/api/drafts/{draft_id}/prediction",
        json={
            "team_id": "team-1",
            "pick_number": 1,
            "candidates": [{"player_id": "player-1"}],
        },
        headers=headers,
    )

    assert response.status_code == 503


def test_unconfigured_recommendation_is_optional_and_manual_pick_still_works(monkeypatch) -> None:
    from app.services.llm_prediction import OpenAICompatiblePredictionProvider

    provider = OpenAICompatiblePredictionProvider(api_key="")
    monkeypatch.setattr("app.api.drafts.OpenAICompatiblePredictionProvider", lambda: provider)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}
    created = client.post(
        "/api/drafts", headers=headers,
        json={"controlled_team_id": "team-1", "draft_year": 2026},
    ).json()
    draft_id = created["draft_run_id"]
    result = client.post(f"/api/drafts/{draft_id}/recommendation", headers=headers)
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "recommendation_not_configured"
    assert "make your pick" in result.json()["detail"]["message"]
    assert "LLM_API_KEY" not in result.text
    assert provider.client.is_closed
    assert client.get(f"/api/drafts/{draft_id}", headers=headers).json()["picks"] == []
    picked = client.post(
        f"/api/drafts/{draft_id}/picks", headers=headers,
        json={"team_id": "team-1", "player_id": created["eligible_players"][0]["player_id"]},
    )
    assert picked.status_code == 201
    assert len(picked.json()["picks"]) == 1


@pytest.mark.parametrize("candidate_id", ["player-1", "missing-player", "wrong-year", "unconfirmed"])
def test_prediction_endpoint_rejects_candidates_outside_available_draft_pool(
    isolate_draft_store: Session, monkeypatch, candidate_id: str,
) -> None:
    """Only eligible, unselected players from this draft year may be prediction candidates."""
    repository = DraftRepository(isolate_draft_store)
    draft = repository.create("user-1", "team-2", 2026)
    repository.add_pick(draft, "team-1", "player-1", "USER")
    if candidate_id in {"wrong-year", "unconfirmed"}:
        isolate_draft_store.add(
            PlayerRecord(
                id=candidate_id,
                first_name="Test",
                last_name="Candidate",
                position="QB",
                college_id="alabama",
                draft_year=2027 if candidate_id == "wrong-year" else 2026,
                eligibility_status="unconfirmed" if candidate_id == "unconfirmed" else "eligible",
            )
        )
    isolate_draft_store.commit()

    class UnexpectedProvider:
        def __init__(self):
            pytest.fail("The prediction provider must not be called for an invalid candidate")

    monkeypatch.setattr("app.api.drafts.OpenAICompatiblePredictionProvider", UnexpectedProvider)
    client = TestClient(app)
    response = client.post(
        f"/api/drafts/{draft.id}/prediction",
        json={
            "team_id": "team-2",
            "pick_number": 2,
            "candidates": [{"player_id": candidate_id}],
        },
        headers={"Authorization": "Bearer " + create_access_token("user-1")},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Prediction candidates must be eligible and not already selected for this draft"


def test_auto_simulation_uses_llm_and_persists_provenance(isolate_draft_store: Session) -> None:
    """Configured model predictions should drive and explain automatic picks."""
    class FakeProvider:
        provider_name = "test-provider"
        model_name = "test-model"

        def complete(self, prompt: str, randomness: float):
            candidate_id = json.loads(prompt)["candidates"][0]["player_id"]
            return {
                "selected_player_id": candidate_id,
                "confidence": 0.81,
                "alternatives": [],
                "reasoning_factors": ["team fit"],
                "evidence": ["test-evidence"],
            }

    repository = DraftRepository(isolate_draft_store, FakeProvider())
    draft = repository.create("user-1", "team-2", 2026, {"team-1": 0}, 25)
    repository.auto_simulate(draft)

    pick = isolate_draft_store.query(DraftPickRecord).filter_by(draft_run_id=draft.id).one()
    assert pick.selection_source == "LLM"
    assert pick.prediction_metadata["model"] == "test-model"


def test_draft_access_is_limited_to_owner() -> None:
    """A different user must not read another user's draft."""
    client = TestClient(app)
    response = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-1", "draft_year": 2026},
        headers={"Authorization": f"Bearer {create_access_token('owner')}"},
    )
    draft_id = response.json()["draft_run_id"]

    response = client.get(
        f"/api/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {create_access_token('user-1')}"},
    )

    assert response.status_code == 403


def test_duplicate_player_selection_is_rejected() -> None:
    """A player cannot be selected more than once in one draft."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}
    draft_id = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-1", "draft_year": 2026},
        headers=headers,
    ).json()["draft_run_id"]

    first = client.post(
        f"/api/drafts/{draft_id}/picks",
        json={"team_id": "team-1", "player_id": "player-1"},
        headers=headers,
    )
    duplicate = client.post(
        f"/api/drafts/{draft_id}/picks",
        json={"team_id": "team-1", "player_id": "player-1"},
        headers=headers,
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409


def test_auto_simulation_uses_latest_team_board_order(isolate_draft_store: Session) -> None:
    """Automatic picks should prefer the generated board for the team on the clock."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('user-1')}"}
    session = isolate_draft_store
    board = TeamBoardRecord(
        team_id="team-1",
        draft_year=2026,
        board_type="default",
        version=1,
        generated_at=datetime.now(UTC),
        scoring_version="test",
        scoring_weights={},
    )
    session.add(board)
    session.flush()
    session.add(TeamBoardEntryRecord(board_id=board.id, player_id="player-3", rank_position=1, score=99, score_breakdown={}))
    session.add(TeamBoardEntryRecord(board_id=board.id, player_id="player-1", rank_position=2, score=90, score_breakdown={}))
    session.commit()

    response = client.post(
        "/api/drafts",
        json={"controlled_team_id": "team-2", "draft_year": 2026, "randomness_overrides": {"team-1": 0}},
        headers=headers,
    )
    draft_id = response.json()["draft_run_id"]
    response = client.post(f"/api/drafts/{draft_id}/auto-simulate", headers=headers)

    assert response.status_code == 200
    assert response.json()["picks"][0]["player_id"] == "player-3"


def test_auto_simulation_reaches_for_a_high_need_within_the_round_limit(isolate_draft_store: Session) -> None:
    """A reachable high-need prospect is prioritized, while BPA remains an option."""
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + create_access_token("user-1")}
    session = isolate_draft_store
    need_prospect = session.get(PlayerRecord, "player-1")
    assert need_prospect is not None
    need_prospect.position = "WR"

    board = TeamBoardRecord(
        team_id="team-1",
        draft_year=2026,
        board_type="default",
        version=1,
        generated_at=datetime.now(UTC),
        scoring_version="test",
        scoring_weights={},
    )
    session.add(board)
    session.flush()
    session.add_all([
        TeamBoardEntryRecord(
            board_id=board.id, player_id="player-3", rank_position=1,
            score=99, score_breakdown={},
        ),
        TeamBoardEntryRecord(
            board_id=board.id, player_id=need_prospect.id, rank_position=13,
            score=90, score_breakdown={},
        ),
        TeamNeedRecord(
            team_id="team-1", draft_year=2026, position_code="WR",
            role_level="starter", need_score=70, source_name="test",
            observed_at=datetime.now(UTC).replace(tzinfo=None),
        ),
    ])
    session.commit()

    created = client.post(
        "/api/drafts",
        json={
            "controlled_team_id": "team-2", "draft_year": 2026,
            "randomness_overrides": {"team-1": 0},
        },
        headers=headers,
    )
    draft_id = created.json()["draft_run_id"]
    response = client.post(f"/api/drafts/{draft_id}/auto-simulate", headers=headers)

    assert response.status_code == 200
    assert response.json()["picks"][0]["player_id"] == need_prospect.id
