"""ASYNC_JOBS=true (Azure): long steps return a job id, GET /api/jobs/<id> gives the result.
Run: pytest tests/test_jobs.py -v"""

import time

import pytest
from fastapi.testclient import TestClient

from backend.core import hosting, jobs
from backend.main import app
from backend.services import scan_service


def fake_scan_store(url, include_mobile=True, config=None, **kwargs):
    return {"store_url": url, "detected_sdk_version": "v5", "pages": [
        {"step": "checkout", "viewport": "desktop", "url": url, "success": True,
         "screenshot_path": f"{config.screenshots_dir}/shot.png", "html": "<html></html>", "paypal_elements": []}]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ASYNC_JOBS", "true")
    monkeypatch.setattr(scan_service, "_reports", {})
    monkeypatch.setattr(scan_service, "scan_store", fake_scan_store)
    monkeypatch.setattr(hosting, "limiter", hosting.RateLimiter(0))
    with TestClient(app) as c:      # keeps one event loop alive, so background jobs can finish
        yield c


def wait_for(client, job_id, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_scan_returns_a_job_then_the_same_result(client):
    started = client.post("/api/scan", json={"store_url": "https://example.com"})
    assert started.status_code == 202
    body = started.json()
    assert body["status"] == "running" and body["stage"] == "Scanning the store"

    job = wait_for(client, body["job_id"])
    assert job["status"] == "succeeded"
    assert job["result"]["paypal_sdk_version"] == "v5" and job["result"]["scan_id"]
    # The saved report is the same one the normal endpoint would have saved.
    assert client.get(f"/api/reports/{job['result']['scan_id']}").status_code == 200


def test_errors_become_failed_jobs_with_the_message(client):
    body = client.post("/api/fix", json={"scan_id": "scan_missing", "issue_ids": ["sdk_outdated"]}).json()
    job = wait_for(client, body["job_id"])
    assert job["status"] == "failed" and job["error"] and job["error_status"] >= 400


def test_a_forged_internal_header_does_not_skip_the_queue(client):
    response = client.post("/api/scan", json={"store_url": "https://example.com"},
                           headers={jobs.INTERNAL_HEADER: "guess"})
    assert response.status_code == 202          # still treated as a normal visitor request


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/job_nope").status_code == 404


def test_off_by_default_answers_directly(monkeypatch):
    monkeypatch.delenv("ASYNC_JOBS", raising=False)
    monkeypatch.setattr(scan_service, "_reports", {})
    monkeypatch.setattr(scan_service, "scan_store", fake_scan_store)
    response = TestClient(app).post("/api/scan", json={"store_url": "https://example.com"})
    assert response.status_code == 200 and response.json()["scan_id"]


def test_stage_names():
    assert jobs._stage("/api/fix/fix_1/rescan") == "Scanning the fixed copy"
    assert jobs._stage("/api/verify") == "Making PayPal Sandbox payments"


def test_strip_port_handles_azure_style_addresses():
    assert hosting.strip_port("203.0.113.7:51234") == "203.0.113.7"
    assert hosting.strip_port("203.0.113.7") == "203.0.113.7"
    assert hosting.strip_port("[2001:db8::1]:443") == "2001:db8::1"
    assert hosting.strip_port("2001:db8::1") == "2001:db8::1"
