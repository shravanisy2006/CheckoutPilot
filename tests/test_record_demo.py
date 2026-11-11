"""The demo recorder saves one real run for Demo Mode, and nothing private. Run: pytest tests/test_record_demo.py -v"""

import json

import pytest

from scripts import record_demo


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "outputs" / "scans" / "s1").mkdir(parents=True)
    (tmp_path / "outputs" / "verifications" / "v1").mkdir(parents=True)
    for name in ("desktop_checkout.png", "mobile_checkout.png"):
        (tmp_path / "outputs" / "scans" / "s1" / name).write_bytes(b"PNG-" + name.encode())
    (tmp_path / "outputs" / "verifications" / "v1" / "02_success_page.png").write_bytes(b"PNG-success")
    samples = [tmp_path / "sample_a.json", tmp_path / "sample_b.json"]
    monkeypatch.setattr(record_demo, "ROOT", tmp_path)
    monkeypatch.setattr(record_demo, "DEMO_IMG_DIR", tmp_path / "public_demo")
    monkeypatch.setattr(record_demo, "SAMPLE_PATHS", samples)
    monkeypatch.setattr(record_demo, "private_values", lambda: ["sb-buyer@personal.example.com", "SECRETPASS1"])
    monkeypatch.setattr(record_demo.requests, "get", lambda *a, **k: type("R", (), {"json": lambda self: {"status": "ok"}})())
    return tmp_path, samples


def _fake_api(monkeypatch, verify_overrides=None):
    pages = [
        {"step": "checkout", "viewport": "desktop", "screenshot_url": "/files/scans/s1/desktop_checkout.png"},
        {"step": "checkout", "viewport": "mobile", "screenshot_url": "/files/scans/s1/mobile_checkout.png"},
    ]
    verify = {"simulated": False, "safe_to_approve": True, "summary": "ok",
              "before": {"order_id": "B1", "screenshots": ["/files/verifications/v1/02_success_page.png"]},
              "after": {"order_id": "A1", "screenshots": ["/files/verifications/v1/02_success_page.png"]}}
    verify.update(verify_overrides or {})

    def call(method, path, body=None, timeout=600):
        if path == "/api/scan":
            return {"scan_id": "s1", "health_score": 21 if body["store_url"].endswith("8101") else 76,
                    "issues": [{"issue_id": "sdk_outdated"}, {"issue_id": "no_paypal_on_cart"}], "pages": pages}
        if path == "/api/fix":
            assert body["issue_ids"] == ["sdk_outdated", "no_paypal_on_cart"]  # only fixable issues found
            return {"fix_id": "fix_1", "files": [{"path": "app.py"}], "generated_by": "template", "browser_check": "passed"}
        if path == "/api/verify":
            return verify
        raise AssertionError(path)

    monkeypatch.setattr(record_demo, "call", call)


def test_saves_a_real_run_with_its_screenshots(project, monkeypatch):
    root, samples = project
    _fake_api(monkeypatch)
    assert record_demo.main([]) == 0
    saved = json.loads(samples[0].read_text())
    assert samples[0].read_text() == samples[1].read_text()
    assert set(saved) == {"_about", "scan", "fix", "verify", "rescan_after_fix"}
    assert saved["rescan_after_fix"]["health_score"] == 76
    # Every /files/ link now points at a copied image under /demo/
    urls = [p["screenshot_url"] for p in saved["scan"]["pages"]]
    assert all(u.startswith("/demo/rec_") for u in urls)
    assert all((root / "public_demo" / u[len("/demo/"):]).exists() for u in urls)
    # The fixed names the dashboard shows
    for name in ("legacy_checkout_desktop.png", "legacy_checkout_mobile.png", "proof_before_v5.png", "proof_after_v6.png"):
        assert (root / "public_demo" / name).exists()


def test_refuses_a_simulated_run(project, monkeypatch):
    _fake_api(monkeypatch, {"simulated": True})
    with pytest.raises(SystemExit, match="SIMULATED"):
        record_demo.main([])
    assert not project[1][0].exists()


def test_refuses_a_failed_verification(project, monkeypatch):
    _fake_api(monkeypatch, {"safe_to_approve": False, "summary": "REGRESSION"})
    with pytest.raises(SystemExit, match="did not pass"):
        record_demo.main([])


def test_never_saves_the_buyer_login(project, monkeypatch):
    _fake_api(monkeypatch, {"buyer": "sb-buyer@personal.example.com"})
    with pytest.raises(SystemExit, match="private value"):
        record_demo.main([])
    assert not project[1][0].exists()
