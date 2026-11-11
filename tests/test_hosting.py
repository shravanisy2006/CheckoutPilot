"""Hosted mode (Render): rate limit, clean-up, dashboard serving, API servers. Run: pytest tests/test_hosting.py -v"""

import os
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import hosting


def test_rate_limiter_allows_the_limit_then_blocks_until_the_window_passes():
    limiter = hosting.RateLimiter(limit=2, window=60)
    assert limiter.allow("1.2.3.4", now=0)[0]
    assert limiter.allow("1.2.3.4", now=1)[0]
    allowed, wait = limiter.allow("1.2.3.4", now=2)
    assert not allowed and 0 < wait <= 60
    assert limiter.allow("5.6.7.8", now=2)[0]          # other visitors are not affected
    assert limiter.allow("1.2.3.4", now=61)[0]          # the first hit has expired


def test_rate_limit_zero_means_off():
    limiter = hosting.RateLimiter(limit=0)
    assert all(limiter.allow("x", now=i)[0] for i in range(100))


def test_only_heavy_posts_are_limited():
    assert hosting.is_heavy("POST", "/api/scan")
    assert hosting.is_heavy("POST", "/api/fix/fix_1/rescan")
    assert hosting.is_heavy("POST", "/api/verify")
    assert not hosting.is_heavy("GET", "/api/fix/fix_1")
    assert not hosting.is_heavy("GET", "/api/health")


def test_middleware_returns_429_with_a_friendly_message(monkeypatch, tmp_path):
    monkeypatch.setattr(hosting, "limiter", hosting.RateLimiter(limit=1))
    app = FastAPI()
    app.middleware("http")(hosting.make_middleware(tmp_path))

    @app.post("/api/scan")
    def scan():
        return {"ok": True}

    client = TestClient(app)
    headers = {"X-Forwarded-For": "9.9.9.9, 10.0.0.1"}
    assert client.post("/api/scan", headers=headers).status_code == 200
    blocked = client.post("/api/scan", headers=headers)
    assert blocked.status_code == 429
    assert "Demo mode" in blocked.json()["detail"] and blocked.headers["Retry-After"]
    # A different visitor still gets through.
    assert client.post("/api/scan", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 200


def test_prune_removes_only_old_run_folders(tmp_path):
    old = tmp_path / "scans" / "scan_old"
    new = tmp_path / "patched" / "fix_new"
    other = tmp_path / "keep_me" / "x"
    for folder in (old, new, other):
        folder.mkdir(parents=True)
    two_days_ago = time.time() - 48 * 3600
    os.utime(old, (two_days_ago, two_days_ago))
    os.utime(other, (two_days_ago, two_days_ago))

    assert hosting.prune_outputs(tmp_path, 24) == 1
    assert not old.exists() and new.exists() and other.exists()
    assert hosting.prune_outputs(tmp_path, 0) == 0     # 0 = off


def _dashboard(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "_shell.html").write_text("<html>shell</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    return tmp_path


def test_dashboard_dir_needs_the_shell(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_DIR", str(tmp_path))
    assert hosting.dashboard_dir() is None
    _dashboard(tmp_path)
    assert hosting.dashboard_dir() == tmp_path.resolve()
    monkeypatch.delenv("DASHBOARD_DIR")
    assert hosting.dashboard_dir() is None


def test_dashboard_serves_files_routes_and_never_escapes(tmp_path):
    folder = tmp_path / "client"
    folder.mkdir()
    folder = _dashboard(folder).resolve()
    (tmp_path / "secret.txt").write_text("nope")

    js = hosting.dashboard_response(folder, "assets/app.js")
    assert Path(js.path).name == "app.js"
    assert Path(hosting.dashboard_response(folder, "audit").path).name == "_shell.html"   # no page: shell
    (folder / "audit").mkdir()
    (folder / "audit" / "index.html").write_text("<html>audit</html>")
    assert Path(hosting.dashboard_response(folder, "audit").path) == folder / "audit" / "index.html"
    assert Path(hosting.dashboard_response(folder, "audit/").path) == folder / "audit" / "index.html"
    assert Path(hosting.dashboard_response(folder, "").path).name == "_shell.html"
    assert Path(hosting.dashboard_response(folder, "../secret.txt").path).name == "_shell.html"
    assert hosting.dashboard_response(folder, "api/nope").status_code == 404


def test_api_servers_lists_the_public_url_first(monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    assert [s["url"] for s in hosting.api_servers()] == ["http://localhost:8000"]
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://checkoutpilot.onrender.com/")
    assert hosting.api_servers()[0]["url"] == "https://checkoutpilot.onrender.com"


def test_demo_stores_only_start_when_asked(monkeypatch):
    monkeypatch.delenv("START_DEMO_STORES", raising=False)
    assert hosting.start_demo_stores() == []


def test_demo_stores_start_from_their_folders(monkeypatch):
    from demo_stores import serve

    started = []
    monkeypatch.setenv("START_DEMO_STORES", "true")
    monkeypatch.setattr(serve, "start_store", lambda folder, port: started.append((folder, port)) or f"http://localhost:{port}")
    assert hosting.start_demo_stores() == ["http://localhost:8101", "http://localhost:8102"]
    assert all((folder / "app.py").is_file() for folder, _ in started)
