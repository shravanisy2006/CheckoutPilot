"""Tests for POST /api/verify and /files (no browser, no PayPal). Run: pytest tests/test_verify_api.py -v"""

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import verify_service
from sandbox_verifier import verify_checkout_mock

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    verify_service._fixes.clear()
    verify_service._verifications.clear()
    yield
    if verify_service._lock.locked():
        verify_service._lock.release()


@pytest.fixture
def mock_verifier(monkeypatch):
    monkeypatch.setenv("MOCK_VERIFIER", "true")


# ------------------------------------------------------------ happy paths ---
def test_compare_legacy_and_upgraded_with_mock(mock_verifier):
    response = client.post("/api/verify", json={"before_store": "legacy", "after_store": "upgraded"})
    assert response.status_code == 200
    body = response.json()
    assert body["safe_to_approve"] is True and body["simulated"] is True
    assert body["before"]["paypal_sdk"] == "v5" and body["after"]["paypal_sdk"] == "v6"
    assert "PayPal SDK v5 -> v6" in body["changes"]
    assert body["before"]["store_url"] == "http://localhost:8101"
    assert body["after"]["store_url"] == "http://localhost:8102"
    assert body["after"]["is_real_sandbox_payment"] is False
    # Saved and retrievable
    again = client.get(f"/api/verify/{body['verification_id']}")
    assert again.status_code == 200 and again.json() == body


def test_after_store_only(mock_verifier):
    body = client.post("/api/verify", json={"after_store": "http://localhost:8102"}).json()
    assert body["before"] is None and body["safe_to_approve"] is True and body["changes"] == []


def test_registered_fix_is_verified(mock_verifier):
    verify_service.register_fix("fix_abc", store="legacy", patched_store="upgraded")
    body = client.post("/api/verify", json={"fix_id": "fix_abc"}).json()
    assert body["fix_id"] == "fix_abc" and body["safe_to_approve"] is True


# ----------------------------------------------------------------- errors ---
def test_unknown_fix_is_404(mock_verifier):
    response = client.post("/api/verify", json={"fix_id": "nope"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FIX_NOT_FOUND"


def test_nothing_to_verify_is_400(mock_verifier):
    response = client.post("/api/verify", json={})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "VERIFY_NO_TARGET"


def test_unknown_store_is_400(mock_verifier):
    response = client.post("/api/verify", json={"after_store": "no-such-store"})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "VERIFY_BAD_STORE"


def test_busy_is_409(mock_verifier):
    verify_service._lock.acquire()
    response = client.post("/api/verify", json={"after_store": "upgraded"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "VERIFY_BUSY"


def test_unknown_verification_is_404():
    assert client.get("/api/verify/does-not-exist").status_code == 404


# ------------------------------------------- real path, with fake browser ---
def test_real_path_starts_and_stops_stores(monkeypatch):
    """Without MOCK_VERIFIER the stores are started, verified, then stopped."""
    monkeypatch.setenv("MOCK_VERIFIER", "false")
    started, stopped, calls = [], [], []

    def fake_verify(url, label="before", page="checkout", headless=True, **_):
        calls.append((url, label, page))
        result = verify_checkout_mock(url, label=label)
        result["warnings"] = []
        result["screenshots"] = [f"outputs/verifications/{label}/02_success_page.png"]
        return result

    monkeypatch.setattr(verify_service, "get_verifier", lambda: fake_verify)
    monkeypatch.setattr(verify_service, "_is_running", lambda url: False)
    monkeypatch.setattr(verify_service, "start_store", lambda folder, port: started.append(port))
    monkeypatch.setattr(verify_service, "stop_store", lambda port: stopped.append(port))

    body = client.post("/api/verify", json={"before_store": "legacy", "after_store": "upgraded", "page": "cart"}).json()
    assert started == [8101, 8102] and stopped == [8101, 8102]
    assert calls == [("http://localhost:8101", "before", "cart"), ("http://localhost:8102", "after", "cart")]
    assert body["simulated"] is False and body["after"]["is_real_sandbox_payment"] is True
    assert body["after"]["screenshots"] == ["/files/verifications/after/02_success_page.png"]


def test_store_is_stopped_even_if_verifier_crashes(monkeypatch):
    monkeypatch.setenv("MOCK_VERIFIER", "false")
    stopped = []

    def crash(*args, **kwargs):
        raise RuntimeError("browser died")

    monkeypatch.setattr(verify_service, "get_verifier", lambda: crash)
    monkeypatch.setattr(verify_service, "_is_running", lambda url: False)
    monkeypatch.setattr(verify_service, "start_store", lambda folder, port: None)
    monkeypatch.setattr(verify_service, "stop_store", lambda port: stopped.append(port))
    with pytest.raises(RuntimeError):
        verify_service.run_verification(verify_service.VerifyRequest(after_store="upgraded"))
    assert stopped == [8102] and not verify_service._lock.locked()


def test_patched_store_folder_gets_a_free_port(tmp_path):
    (tmp_path / "app.py").write_text("app = None")
    url, folder, port = verify_service.resolve_target(str(tmp_path))
    assert folder == tmp_path.resolve() and url == f"http://localhost:{port}" and port > 0


# -------------------------------------------------------------- /files ---
def test_to_file_url():
    assert verify_service.to_file_url("outputs/verifications/x/01.png") == "/files/verifications/x/01.png"
    assert verify_service.to_file_url(r"C:\Projects\CheckoutPilot\outputs\verifications\x\01.png") == \
        "/files/verifications/x/01.png"


def test_files_route_serves_outputs():
    folder = Path("outputs") / "_test_files_route"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "hello.txt").write_text("hi")
    try:
        response = client.get("/files/_test_files_route/hello.txt")
        assert response.status_code == 200 and response.text == "hi"
        assert client.get("/files/_test_files_route/missing.txt").status_code == 404
    finally:
        (folder / "hello.txt").unlink()
        folder.rmdir()


def test_only_one_verification_at_a_time(mock_verifier, monkeypatch):
    """Two requests at once: one runs, the other gets VERIFY_BUSY."""
    gate = threading.Event()
    release = threading.Event()

    def slow(url, label="before", **_):
        gate.set()
        release.wait(5)
        return verify_checkout_mock(url, label=label)

    monkeypatch.setattr(verify_service, "get_verifier", lambda: slow)
    results = {}
    worker = threading.Thread(target=lambda: results.setdefault(
        "first", client.post("/api/verify", json={"after_store": "upgraded"}).status_code))
    worker.start()
    gate.wait(5)
    results["second"] = client.post("/api/verify", json={"after_store": "upgraded"}).status_code
    release.set()
    worker.join(5)
    assert results == {"first": 200, "second": 409}
