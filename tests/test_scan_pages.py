"""Scan screenshots are saved where the backend serves them. Run: pytest tests/test_scan_pages.py -v"""

from fastapi.testclient import TestClient

from backend.main import app
from backend.services import scan_service

client = TestClient(app)


def test_screenshots_are_saved_under_outputs_scans_and_linked(monkeypatch):
    monkeypatch.setattr(scan_service, "_reports", {})
    seen = {}

    def fake_scan_store(url, include_mobile=True, config=None, **kwargs):
        seen["dir"] = config.screenshots_dir.replace("\\", "/")
        shot = f"{config.screenshots_dir}/scan_1_desktop_checkout.png"
        return {
            "store_url": url,
            "detected_sdk_version": "v5",
            "pages": [
                {"step": "checkout", "viewport": "desktop", "url": url, "success": True,
                 "screenshot_path": shot, "html": "<html>page source</html>", "paypal_elements": []},
            ],
        }

    monkeypatch.setattr(scan_service, "scan_store", fake_scan_store)
    body = client.post("/api/scan", json={"store_url": "https://example.com"}).json()

    # The scanner was told to save into outputs/scans/<scan_id>/ ...
    assert seen["dir"] == f"outputs/scans/{body['scan_id']}"
    # ... which is exactly where the screenshot link points (served by /files).
    assert body["pages"][0]["screenshot_url"] == f"/files/scans/{body['scan_id']}/scan_1_desktop_checkout.png"
    assert body["paypal_sdk_version"] == "v5"
    assert "html" not in body["pages"][0]  # page source is never sent to the dashboard
