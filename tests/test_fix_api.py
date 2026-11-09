"""Tests for POST /api/fix and the code agent's safety rules. Run: pytest tests/test_fix_api.py -v"""

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import fix_service, verify_service
from code_agent import generate_upgrade
from code_agent.fix_builder import build_fix

client = TestClient(app)
LEGACY = Path("demo_stores/legacy_store")


def _fingerprint(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.as_posix().encode() + path.read_bytes())
    return digest.hexdigest()


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Tests use the built-in template planner (no AI calls, no keys)."""
    monkeypatch.setenv("CODE_AGENT_PROVIDER", "deterministic")
    fix_service._fixes.clear()
    verify_service._fixes.clear()


def test_build_fix_patches_a_copy_only(tmp_path):
    before = _fingerprint(LEGACY)
    fix = build_fix(LEGACY, ["sdk_outdated", "no_paypal_on_cart", "button_below_fold_mobile"],
                    fix_id="fix_test", out_root=tmp_path)
    assert _fingerprint(LEGACY) == before  # original untouched
    assert fix["status"] == "proposed" and fix["errors"] == []
    assert fix["generated_by"] == "template" and fix["pr_url"] == ""
    patched = tmp_path / "fix_test"
    assert "web-sdk/v6" in (patched / "app.py").read_text(encoding="utf-8")
    assert "paypal.com/sdk/js" not in (patched / "templates" / "checkout.html").read_text(encoding="utf-8")
    paths = {f["path"] for f in fix["files"]}
    assert {"templates/checkout.html", "templates/cart.html", "static/paypal.js"} <= paths
    assert all(f["diff"] and f["change_type"] in ("added", "modified", "deleted") for f in fix["files"])
    assert {e["issue_id"] for e in fix["explanation"]} == {"sdk_outdated", "no_paypal_on_cart",
                                                           "button_below_fold_mobile"}


def test_build_fix_under_an_outputs_folder(tmp_path):
    """The real copy lives in outputs/patched/: files there must still be compared."""
    fix = build_fix(LEGACY, ["sdk_outdated"], fix_id="fix_out", out_root=tmp_path / "outputs" / "patched")
    assert fix["status"] == "proposed"
    assert not any(f["change_type"] == "deleted" for f in fix["files"])


def test_agent_refuses_to_patch_the_project_itself():
    before = _fingerprint(LEGACY)
    result = generate_upgrade(".", None)
    assert result["success"] is False and result["files_changed"] == []
    assert _fingerprint(LEGACY) == before
    assert not Path("paypal.js").exists()


def test_empty_plan_changes_nothing(tmp_path):
    assert generate_upgrade(str(tmp_path), [])["files_changed"] == []


def test_fix_route_registers_fix_for_verify(monkeypatch, tmp_path):
    monkeypatch.setattr("code_agent.fix_builder.PATCHED_ROOT", tmp_path)
    import code_agent.fix_builder as fb
    original = fb.build_fix
    monkeypatch.setattr(fb, "build_fix", lambda *a, **k: original(*a, **{**k, "out_root": tmp_path}))

    response = client.post("/api/fix", json={"store": "legacy"})
    assert response.status_code == 200
    fix = response.json()
    assert fix["status"] == "proposed" and fix["fix_id"].startswith("fix_")
    assert verify_service._fixes[fix["fix_id"]]["store"] == "legacy"
    assert client.get(f"/api/fix/{fix['fix_id']}").json() == fix

    monkeypatch.setenv("MOCK_VERIFIER", "true")
    verified = client.post("/api/verify", json={"fix_id": fix["fix_id"]}).json()
    assert verified["fix_id"] == fix["fix_id"] and verified["safe_to_approve"] is True


def test_fix_errors():
    assert client.post("/api/fix", json={"store": "nope"}).status_code == 400
    assert client.post("/api/fix", json={"scan_id": "missing"}).json()["detail"]["code"] == "FIX_NO_STORE"
    assert client.get("/api/fix/missing").status_code == 404


def test_failed_upgrade_is_an_error(monkeypatch):
    import code_agent.fix_builder as fb
    monkeypatch.setattr(fb, "build_fix", lambda *a, **k: {"fix_id": "fix_bad", "status": "failed",
                                                          "errors": ["No PayPal SDK v6 code found"]})
    response = client.post("/api/fix", json={"store": "legacy"})
    assert response.status_code == 500 and response.json()["detail"]["code"] == "FIX_FAILED"
    assert "fix_bad" not in verify_service._fixes


def _fake_ai(plan_json: str):
    from code_agent.llm_client import BaseLLMAdapter

    class FakeAI(BaseLLMAdapter):
        def is_available(self):
            return True

        def generate_text(self, prompt, system_prompt=None):
            return plan_json

    return FakeAI()


def test_ai_plan_is_labelled_honestly(tmp_path, monkeypatch):
    from code_agent.agentic import coding_agent
    plan = '[{"gap_id": "sdk_outdated", "file": "README.md", "before_snippet": "Inkwell", "after_snippet": "Inkwell"}]'
    monkeypatch.setattr(coding_agent, "get_llm_client", lambda: _fake_ai(plan))
    fix = build_fix(LEGACY, ["sdk_outdated"], fix_id="fix_ai", out_root=tmp_path)
    assert fix["status"] == "proposed" and fix["generated_by"] == "ai+template"


def test_ai_plan_cannot_write_outside_the_copy(tmp_path, monkeypatch):
    from code_agent.agentic import coding_agent
    outside = tmp_path / "outside.txt"
    outside.write_text("keep me")
    plan = ('[{"gap_id": "sdk_outdated", "file": "../outside.txt", "before_snippet": "keep me",'
            ' "after_snippet": "hacked"}]')
    monkeypatch.setattr(coding_agent, "get_llm_client", lambda: _fake_ai(plan))
    fix = build_fix(LEGACY, ["sdk_outdated"], fix_id="fix_escape", out_root=tmp_path)
    assert outside.read_text() == "keep me"
    assert fix["status"] == "proposed"


def test_ai_that_breaks_a_page_falls_back_to_template(tmp_path, monkeypatch):
    """An AI rewrite that drops element ids (seen with a real model) must not be accepted."""
    from code_agent.agentic import coding_agent
    plan = ('[{"gap_id": "no_paypal_on_cart", "file": "templates/cart.html",'
            ' "before_snippet": "id=\\"cart-total\\"", "after_snippet": "class=\\"total\\""}]')
    monkeypatch.setattr(coding_agent, "get_llm_client", lambda: _fake_ai(plan))
    fix = build_fix(LEGACY, ["sdk_outdated", "no_paypal_on_cart"], fix_id="fix_break", out_root=tmp_path)
    assert fix["status"] == "proposed" and fix["generated_by"] == "template"
    assert "lost element ids" in fix["warnings"][0]
    assert 'id="cart-total"' in (tmp_path / "fix_break" / "templates" / "cart.html").read_text(encoding="utf-8")
