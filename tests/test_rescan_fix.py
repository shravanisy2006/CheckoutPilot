"""Re-measure: scan the code agent's patched copy. Run: pytest tests/test_rescan_fix.py -v"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import fix_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    fix_service._fixes.clear()
    monkeypatch.setenv("CODE_AGENT_PROVIDER", "deterministic")
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    monkeypatch.setenv("AI_VISION_ENABLED", "false")
    import code_agent.fix_builder as fb
    original = fb.build_fix
    monkeypatch.setattr(fb, "build_fix", lambda *a, **k: original(*a, **{**k, "out_root": tmp_path}))
    yield
    fix_service._fixes.clear()


def test_unknown_fix_is_404():
    response = client.post("/api/fix/nope/rescan")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "FIX_NOT_FOUND"


def test_rescan_shows_the_fix_worked():
    """Real scanner on the real patched copy: v6, PayPal on the cart, PayPal visible on mobile."""
    fix = client.post("/api/fix", json={"store": "legacy",
                                        "issue_ids": ["sdk_outdated", "no_paypal_on_cart", "button_below_fold_mobile"]})
    assert fix.status_code == 200, fix.text
    fix_id = fix.json()["fix_id"]

    rescan = client.post(f"/api/fix/{fix_id}/rescan")
    assert rescan.status_code == 200, rescan.text
    body = rescan.json()
    assert body["status"] == "completed" and body["rescan_of_fix"] == fix_id
    assert body["paypal_sdk_version"] == "v6"
    remaining = {i["issue_id"] for i in body["issues"]}
    assert not remaining & {"sdk_outdated", "no_paypal_on_cart", "button_below_fold_mobile"}
    assert body["health_score"] >= 70
    assert client.get(f"/api/fix/{fix_id}").json()["rescan"]["scan_id"] == body["scan_id"]
