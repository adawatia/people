from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "HRMS API"}


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "hrms-api"
    assert isinstance(payload["uptime_seconds"], (int, float))
    assert isinstance(payload["response_time_ms"], (int, float))
    assert payload["database"]["status"] in {"connected", "disconnected"}
