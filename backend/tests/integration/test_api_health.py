from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_200_and_expected_shape():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "providers" in body
    assert "duckduckgo" in body["providers"]
    assert "tavily" in body["providers"]
    assert "llm" in body


def test_providers_status_endpoint_returns_per_provider_state():
    with TestClient(app) as client:
        response = client.get("/api/providers/status")
    assert response.status_code == 200
    body = response.json()
    providers = {p["name"]: p for p in body["providers"]}
    assert "duckduckgo" in providers
    assert "tavily" in providers
    assert all(p["enabled"] is True for p in body["providers"])
    # every registered provider should report a circuit breaker state
    assert all("circuit_breaker_state" in p for p in body["providers"])
