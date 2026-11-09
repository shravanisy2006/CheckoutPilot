"""Scan results include per-page screenshots the dashboard can show. Run: pytest tests/test_scan_pages.py -v"""

from fastapi.testclient import TestClient

from backend.main import app
from backend.services import scan_service

client = TestClient(app)


def test_scan_returns_pages_with_screenshot_urls(monkeypatch):
    monkeypatch.setattr(scan_service, "_reports", {})
    seen = {}

    def fake_scan_store(url, include_mobile=True, config=None, **kwargs):
        seen["dir"] = config.screenshots_dir.replace("\\", "/")
        shot = r"C:\Projects\CheckoutPilot\outputs\scans\abc\checkout_desktop.png"
        return {
            "store_url": url,
            "detected_sdk_version": "v5",
            "pages": [
                {"step": "checkout", "viewport": "desktop", "url": url, "success": True,
                 "screenshot_path": shot, "html": "<html>secret page source</html>"},
                {"step": "cart", "viewport": "mobile", "url": url, "success": False,
                 "screenshot_path": "", "error": "timeout"},
            ],
        }

    monkeypatch.setattr(scan_service, "scan_store", fake_scan_store)
    body = client.post("/api/scan", json={"store_url": "https://example.com"}).json()

    assert seen["dir"] == f"outputs/scans/{body['scan_id']}"
    assert body["paypal_sdk_version"] == "v5"
    assert body["pages"][0]["screenshot_url"] == "/files/scans/abc/checkout_desktop.png"
    assert body["pages"][1] == {"step": "cart", "viewport": "mobile", "url": "https://example.com",
                                "success": False, "error": "timeout", "screenshot_url": ""}
    assert "html" not in body["pages"][0]  # page source is never sent to the dashboard


def test_paths_outside_outputs_are_not_served():
    assert scan_service._file_url("screenshots/x.png") == ""
