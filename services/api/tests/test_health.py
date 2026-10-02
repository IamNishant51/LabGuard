"""M1 health-endpoint tests: normal response shape and no-secret leakage."""

from fastapi.testclient import TestClient

from labguard_api.main import app

client = TestClient(app)


def test_health_returns_200_with_status_and_server_time() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "server_time" in body
    assert "T" in body["server_time"]  # ISO-8601 UTC timestamp


def test_health_exposes_no_secrets() -> None:
    body = client.get("/api/v1/health").json()
    blob = str(body).lower()
    for forbidden in ("password", "secret", "token", "postgres", "database_url"):
        assert forbidden not in blob


def test_unknown_route_is_404() -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404
