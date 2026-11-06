"""Tests for the backend API. Run from the project root with:  pytest"""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_root_returns_message():
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_health_check_is_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_scan_returns_placeholder():
    response = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["store_url"] == "https://example.com"
    assert body["status"] == "placeholder"
    assert isinstance(body["gaps"], list)


def test_scan_requires_store_url():
    response = client.post("/api/scan", json={})
    assert response.status_code == 422  # validation error
