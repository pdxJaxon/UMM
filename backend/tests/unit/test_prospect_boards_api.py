"""Read-only snapshot review, stable rank comparisons, and access control."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db.initialize import seed_reference_data
from app.db.models import PlayerRecord, ProspectBoardSnapshotRecord, UserRecord
from app.db.session import Base, get_db
from app.main import app
from app.services.pff_snapshot import PFFBoardSnapshot
from app.services.prospect_board_import import import_board_snapshot


@pytest.fixture
def review_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_reference_data(session)

        def database():
            yield session

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = lambda: UserRecord(id="review-user")
        try:
            with TestClient(app) as client:
                yield client, session
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
    engine.dispose()


def snapshot(day=0, names=("Alpha Prospect", "Beta Prospect"), year=2027):
    return PFFBoardSnapshot.model_validate({
        "source_url": f"https://www.pff.com/draft/big-board?season={year}",
        "draft_year": year,
        "collected_at": datetime(2026, 10, 14, tzinfo=UTC) + timedelta(days=day),
        "collection_method": "synthetic test fixture",
        "scope": "Synthetic test rows only",
        "source_updated_at_display": None,
        "prospects": [
            {"overall_rank": rank, "name": name, "school": "Alabama", "position": "HB",
             "pff_grade": None if rank == 1 else 0}
            for rank, name in enumerate(names, start=1)
        ],
    })


def test_requires_authentication(review_client):
    client, _ = review_client
    app.dependency_overrides.pop(get_current_user)
    assert client.get("/api/prospect-boards/pff/latest?draft_year=2027").status_code == 401


def test_empty_review_is_explicit_and_read_only(review_client):
    client, session = review_client
    response = client.get("/api/prospect-boards/pff/latest?draft_year=2027")
    assert response.status_code == 200
    assert response.json() == {
        "source": "pff-big-board", "draft_year": 2027, "snapshot": None,
        "previous_snapshot": None, "entries": [],
    }
    assert session.query(PlayerRecord).count() == 0


def test_first_snapshot_has_no_comparison_and_preserves_null_and_zero(review_client):
    client, session = review_client
    import_board_snapshot(session, snapshot(), commit=True)
    data = client.get("/api/prospect-boards/pff/latest?draft_year=2027").json()
    assert data["previous_snapshot"] is None
    assert data["snapshot"]["collected_at"].endswith("Z")
    assert data["snapshot"]["scope"] == "Synthetic test rows only"
    assert data["snapshot"]["source_url"].endswith("season=2027")
    assert [row["pff_grade"] for row in data["entries"]] == [None, 0]
    assert all(row["rank_change"] is None and row["previous_rank"] is None for row in data["entries"])
    assert all(row["eligibility_status"] == "unconfirmed" for row in data["entries"])
    assert all(row["source_position"] == "HB" and row["canonical_position"] == "RB" for row in data["entries"])


def test_rank_changes_use_stable_ids_and_collection_order_not_import_order(review_client):
    client, session = review_client
    import_board_snapshot(session, snapshot(2, ("Beta Prospect", "New Prospect", "Alpha Prospect")), commit=True)
    import_board_snapshot(session, snapshot(0, ("Old Prospect",)), commit=True)
    import_board_snapshot(session, snapshot(1), commit=True)
    before = session.query(ProspectBoardSnapshotRecord).count()
    data = client.get("/api/prospect-boards/pff/latest?draft_year=2027").json()
    assert [row["name"] for row in data["entries"]] == ["Beta Prospect", "New Prospect", "Alpha Prospect"]
    assert [row["previous_rank"] for row in data["entries"]] == [2, None, 1]
    assert [row["rank_change"] for row in data["entries"]] == [1, None, -2]
    assert data["previous_snapshot"]["collected_at"].startswith("2026-10-15")
    assert data["snapshot"]["collected_at"].startswith("2026-10-16")
    assert session.query(ProspectBoardSnapshotRecord).count() == before
    assert session.query(PlayerRecord).count() == 4


def test_unchanged_rank_and_current_eligibility_are_reported_without_mutation(review_client):
    client, session = review_client
    import_board_snapshot(session, snapshot(), commit=True)
    import_board_snapshot(session, snapshot(1), commit=True)
    player = session.scalar(select(PlayerRecord).where(PlayerRecord.first_name == "Alpha"))
    player.eligibility_status = "eligible"
    session.commit()
    data = client.get("/api/prospect-boards/pff/latest?draft_year=2027").json()
    assert [row["rank_change"] for row in data["entries"]] == [0, 0]
    assert [row["eligibility_status"] for row in data["entries"]] == ["eligible", "unconfirmed"]
    assert session.get(PlayerRecord, player.id).eligibility_status == "eligible"


def test_other_seasons_and_sources_do_not_leak_into_comparison(review_client):
    client, session = review_client
    import_board_snapshot(session, snapshot(), commit=True)
    import_board_snapshot(session, snapshot(5, ("Future Prospect",), year=2028), commit=True)
    session.add(ProspectBoardSnapshotRecord(
        id="other-source", source_name="other", content_hash="other-hash",
        source_url="https://example.com", draft_year=2027,
        collected_at=datetime(2026, 11, 1), collection_method="fixture", scope="other", prospect_count=1,
    ))
    session.commit()
    data = client.get("/api/prospect-boards/pff/latest?draft_year=2027").json()
    assert data["snapshot"]["collected_at"].startswith("2026-10-14")
    assert data["previous_snapshot"] is None
    assert len(data["entries"]) == 2
    assert client.get("/api/prospect-boards/pff/latest?draft_year=2029").json()["snapshot"] is None


@pytest.mark.parametrize("query", ["", "?draft_year=2019", "?draft_year=2101", "?draft_year=abc"])
def test_invalid_season_is_rejected(review_client, query):
    client, _ = review_client
    assert client.get("/api/prospect-boards/pff/latest" + query).status_code == 422
