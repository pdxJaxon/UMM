from fastapi.testclient import TestClient

from app.main import app
from app.services.ranking_service import calculate_umm_ranking


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_cors_rejects_untrusted_origin() -> None:
    response = TestClient(app).options(
        "/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_umm_ranking_uses_weighted_average() -> None:
    values = {
        "pff": 90,
        "nfl": 80,
        "sparq": 70,
        "school_affinity": 85,
        "team_connection": 95,
    }

    result = calculate_umm_ranking(values)

    assert result > 0
    assert result <= 100
