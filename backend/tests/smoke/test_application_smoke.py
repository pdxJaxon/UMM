"""Fast checks for the critical application paths."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.smoke
def test_api_health_check() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.smoke
def test_protected_draft_endpoint_rejects_anonymous_request() -> None:
    response = TestClient(app).post(
        "/api/drafts",
        json={"controlled_team_id": "team-1", "draft_year": 2026},
    )

    assert response.status_code == 401