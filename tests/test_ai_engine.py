"""
Tests for the AI engine (Member 4).

The vision model is replaced by fake callers, so these tests never call a
real AI API and run offline. Run with:  pytest tests/test_ai_engine.py -v
"""

import copy
import json
from pathlib import Path

import pytest

from ai_engine import analyze_checkout, analyze_checkout_detailed, analyze_checkout_mock
from ai_engine.errors import AI_BAD_OUTPUT, ModuleError
from ai_engine.rules import run_rule_checks
from ai_engine.vision import clear_cache, parse_model_output, run_vision_checks

FIXTURES = Path(__file__).parent / "fixtures"
REQUIRED_KEYS = {"issue_id", "title", "category", "severity", "source", "evidence",
                 "screenshot_path", "fixable_by_agent", "confidence"}


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fresh_cache():
    """Make sure cached vision answers from one test never leak into another."""
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def legacy_with_screenshots(tmp_path):
    """Legacy ScanData whose cart/checkout screenshots really exist on disk."""
    data = load("scan_data_legacy.json")
    for page in data["pages"]:
        image = tmp_path / f"{page['step']}_{page['viewport']}.png"
        image.write_bytes(b"\x89PNG fake " + page["step"].encode() + page["viewport"].encode())
        page["screenshot_path"] = str(image)
    return data


def fake_caller(*replies):
    """Return a caller that gives each reply in turn and counts its calls."""
    calls = {"count": 0}

    def call(system, prompt, images):
        reply = replies[min(calls["count"], len(replies) - 1)]
        calls["count"] += 1
        return reply

    call.calls = calls
    return call


GOOD_REPLY = json.dumps({"issues": [
    {"issue_id": "paypal_button_not_prominent", "title": "PayPal button is hard to notice",
     "severity": "medium", "evidence": "Grey button below the card form.", "confidence": 0.8,
     "screenshot_index": 2},
    {"issue_id": "no_paypal_on_cart", "title": "No PayPal on cart", "severity": "high",
     "evidence": "Cart shows only a card checkout button.", "confidence": 0.9, "screenshot_index": 0},
]})


# ---------------------------------------------------------------- rules -----
def test_legacy_store_flags_high_issues():
    issues = run_rule_checks(load("scan_data_legacy.json"))
    by_id = {issue["issue_id"]: issue for issue in issues}
    assert by_id["sdk_outdated"]["severity"] == "high"
    assert by_id["no_paypal_on_cart"]["severity"] == "high"
    assert "button_below_fold_mobile" in by_id
    assert "no_paypal_on_product" in by_id


def test_upgraded_store_has_no_high_issues():
    issues = run_rule_checks(load("scan_data_upgraded.json"))
    assert [i for i in issues if i["severity"] == "high"] == []


def test_issues_match_checkout_issue_shape():
    for issue in run_rule_checks(load("scan_data_legacy.json")):
        assert REQUIRED_KEYS <= set(issue)
        assert issue["severity"] in {"high", "medium", "low"}
        assert issue["source"] == "rule"


def test_empty_scan_gives_no_issues():
    assert run_rule_checks({"store_url": "x", "pages": []}) == []


def test_rules_are_deterministic():
    data = load("scan_data_legacy.json")
    assert run_rule_checks(copy.deepcopy(data)) == run_rule_checks(copy.deepcopy(data))


# ------------------------------------------------------- vision parsing -----
def test_parse_valid_reply():
    issues = parse_model_output(GOOD_REPLY)
    assert [i.issue_id for i in issues] == ["paypal_button_not_prominent", "no_paypal_on_cart"]


def test_parse_reply_inside_code_fence():
    assert len(parse_model_output("```json\n" + GOOD_REPLY + "\n```")) == 2


@pytest.mark.parametrize("bad", [
    "not json at all",
    '{"issues": "nope"}',
    '{"issues": [{"issue_id": "made_up_issue", "title": "x", "severity": "high", "confidence": 1}]}',
    '{"issues": [{"issue_id": "paypal_button_cluttered", "title": "x", "severity": "huge", "confidence": 1}]}',
    '{"issues": [{"issue_id": "paypal_button_cluttered", "title": "x", "severity": "low", "confidence": 7}]}',
])
def test_parse_rejects_bad_replies(bad):
    with pytest.raises(ModuleError) as error:
        parse_model_output(bad)
    assert error.value.code == AI_BAD_OUTPUT


# ------------------------------------------------------- vision calls -------
def test_vision_valid_reply(legacy_with_screenshots):
    caller = fake_caller(GOOD_REPLY)
    issues, warnings = run_vision_checks(legacy_with_screenshots, caller)
    assert caller.calls["count"] == 1
    assert {i["source"] for i in issues} == {"vision"}
    assert all(Path(i["screenshot_path"]).is_file() for i in issues)


def test_vision_retries_once_after_bad_reply(legacy_with_screenshots):
    caller = fake_caller("garbage", GOOD_REPLY)
    issues, _ = run_vision_checks(legacy_with_screenshots, caller)
    assert caller.calls["count"] == 2
    assert len(issues) == 2


def test_vision_gives_up_after_two_bad_replies(legacy_with_screenshots):
    caller = fake_caller("garbage", "still garbage")
    with pytest.raises(ModuleError) as error:
        run_vision_checks(legacy_with_screenshots, caller)
    assert error.value.code == AI_BAD_OUTPUT
    assert caller.calls["count"] == 2


def test_vision_skipped_without_screenshots():
    caller = fake_caller(GOOD_REPLY)
    issues, warnings = run_vision_checks(load("scan_data_legacy.json"), caller)  # paths don't exist
    assert issues == [] and caller.calls["count"] == 0


def test_vision_results_are_cached(legacy_with_screenshots):
    caller = fake_caller(GOOD_REPLY)
    first, _ = run_vision_checks(legacy_with_screenshots, caller)
    second, _ = run_vision_checks(legacy_with_screenshots, caller)
    assert first == second and caller.calls["count"] == 1


# ------------------------------------------------------- full analyzer ------
def test_bad_ai_output_keeps_rule_issues(legacy_with_screenshots):
    result = analyze_checkout_detailed(legacy_with_screenshots, fake_caller("garbage", "garbage"))
    ids = {i["issue_id"] for i in result["issues"]}
    assert {"sdk_outdated", "no_paypal_on_cart"} <= ids
    assert any(w.startswith("AI_BAD_OUTPUT") for w in result["warnings"])


def test_rule_and_vision_duplicates_are_merged(legacy_with_screenshots):
    result = analyze_checkout_detailed(legacy_with_screenshots, fake_caller(GOOD_REPLY))
    ids = [i["issue_id"] for i in result["issues"]]
    assert ids.count("no_paypal_on_cart") == 1
    merged = next(i for i in result["issues"] if i["issue_id"] == "no_paypal_on_cart")
    assert merged["source"] == "rule+vision"
    assert "paypal_button_not_prominent" in ids


def test_missing_api_key_gives_warning_not_crash(legacy_with_screenshots, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    result = analyze_checkout_detailed(legacy_with_screenshots)
    assert any(w.startswith("AI_UNAVAILABLE") for w in result["warnings"])
    assert {"sdk_outdated", "no_paypal_on_cart"} <= {i["issue_id"] for i in result["issues"]}


def test_analyze_checkout_contract_returns_list_and_records_warnings(legacy_with_screenshots, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    issues = analyze_checkout(legacy_with_screenshots)
    assert isinstance(issues, list)
    assert any(w.startswith("AI_UNAVAILABLE") for w in legacy_with_screenshots["warnings"])


def test_vision_can_be_switched_off(legacy_with_screenshots, monkeypatch):
    monkeypatch.setenv("AI_VISION_ENABLED", "false")
    caller = fake_caller(GOOD_REPLY)
    result = analyze_checkout_detailed(legacy_with_screenshots, caller)
    assert caller.calls["count"] == 0 and result["warnings"] == []


# ------------------------------------------------------- mock --------------
def test_mock_returns_fixture_issues():
    ids = {i["issue_id"] for i in analyze_checkout_mock()}
    assert {"sdk_outdated", "no_paypal_on_cart"} <= ids


def test_mock_upgraded_store_is_clean():
    assert analyze_checkout_mock({"paypal_sdk_version": "v6"}) == []


# ------------------------------------------------------- try_vision tool ----
def test_try_vision_builds_scan_data(tmp_path):
    from ai_engine.try_vision import build_scan_data

    image = tmp_path / "shot.png"
    image.write_bytes(b"png")
    data = build_scan_data([str(image), str(image)], ["cart (mobile)"])
    assert [(p["step"], p["viewport"]) for p in data["pages"]] == [("cart", "mobile"), ("checkout", "desktop")]


def test_try_vision_reports_missing_file(capsys):
    from ai_engine.try_vision import main

    assert main(["does_not_exist.png"]) == 1
    assert "File not found" in capsys.readouterr().out


def test_try_vision_reports_missing_key(tmp_path, monkeypatch, capsys):
    from ai_engine.try_vision import main

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    image = tmp_path / "shot.png"
    image.write_bytes(b"png")
    assert main([str(image)]) == 2
    assert "AI_UNAVAILABLE" in capsys.readouterr().out


# ------------------------------------------------------- retries / fallback --
class _Reply:
    def __init__(self, status, payload=None):
        self.status_code = status
        self.text = json.dumps(payload or {"error": "busy"})
        self._payload = payload or {}

    def json(self):
        return self._payload


GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": GOOD_REPLY}]}}]}


@pytest.fixture
def gemini_env(monkeypatch, legacy_with_screenshots):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("AI_FALLBACK_MODEL", raising=False)
    monkeypatch.setattr("ai_engine.vision.time.sleep", lambda seconds: None)
    return legacy_with_screenshots


def test_busy_reply_is_retried_then_succeeds(gemini_env, monkeypatch):
    replies = iter([_Reply(503), _Reply(200, GEMINI_OK)])
    monkeypatch.setattr("ai_engine.vision.requests.post", lambda *a, **k: next(replies))
    issues, _ = run_vision_checks(gemini_env)
    assert len(issues) == 2


def test_busy_three_times_gives_ai_unavailable(gemini_env, monkeypatch):
    calls = []
    monkeypatch.setattr("ai_engine.vision.requests.post", lambda *a, **k: calls.append(1) or _Reply(503))
    with pytest.raises(ModuleError) as error:
        run_vision_checks(gemini_env)
    assert error.value.code == "AI_UNAVAILABLE" and len(calls) == 3


def test_fallback_model_used_when_main_model_busy(gemini_env, monkeypatch):
    monkeypatch.setenv("AI_FALLBACK_MODEL", "backup-model")
    urls = []

    def fake_post(url, **kwargs):
        urls.append(url)
        return _Reply(200, GEMINI_OK) if "backup-model" in url else _Reply(503)

    monkeypatch.setattr("ai_engine.vision.requests.post", fake_post)
    issues, _ = run_vision_checks(gemini_env)
    assert len(issues) == 2 and "backup-model" in urls[-1]


def test_bad_key_is_not_retried(gemini_env, monkeypatch):
    calls = []
    monkeypatch.setattr("ai_engine.vision.requests.post", lambda *a, **k: calls.append(1) or _Reply(400))
    with pytest.raises(ModuleError):
        run_vision_checks(gemini_env)
    assert len(calls) == 1


def test_list_models_filters_to_generate_content(monkeypatch, capsys):
    from ai_engine.try_vision import main

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    payload = {"models": [
        {"name": "models/model-b", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/embed-only", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/model-a", "supportedGenerationMethods": ["generateContent", "countTokens"]},
    ]}
    monkeypatch.setattr("ai_engine.vision.requests.get", lambda *a, **k: _Reply(200, payload))
    assert main(["--list-models"]) == 0
    out = capsys.readouterr().out
    assert "model-a" in out and "model-b" in out and "embed-only" not in out


# ---- Roshan's scanner format (detected_sdk_version + bounding_box) -------------------
from ai_engine.rules import get_sdk_version, is_visible_without_scroll, run_rule_checks as _rules


def _scanner_page(step, viewport, y=None, category="button"):
    elements = [] if y is None else [{"category": category, "visible": True,
                                      "bounding_box": {"x": 10, "y": y, "width": 300, "height": 45}}]
    return {"step": step, "viewport": viewport, "screenshot_path": "", "paypal_elements": elements}


def test_scanner_format_legacy_store_finds_all_four():
    scan = {"detected_sdk_version": "v5", "pages": [
        _scanner_page("product", "desktop"), _scanner_page("cart", "desktop"),
        _scanner_page("checkout", "desktop", 331), _scanner_page("product", "mobile"),
        _scanner_page("cart", "mobile"), _scanner_page("checkout", "mobile", 1339.5)]}
    assert {i["issue_id"] for i in _rules(scan)} == {
        "sdk_outdated", "no_paypal_on_cart", "no_paypal_on_product", "button_below_fold_mobile"}


def test_scanner_format_upgraded_store_has_no_false_alarm():
    scan = {"detected_sdk_version": "v6", "pages": [
        _scanner_page("product", "desktop"), _scanner_page("cart", "desktop", 380),
        _scanner_page("checkout", "desktop", 330), _scanner_page("product", "mobile"),
        _scanner_page("cart", "mobile", 400), _scanner_page("checkout", "mobile", 340)]}
    assert {i["issue_id"] for i in _rules(scan)} == {"no_paypal_on_product"}


def test_unknown_version_and_pay_later_text_are_not_buttons():
    assert get_sdk_version({"detected_sdk_version": "unknown"}) == "none"
    assert get_sdk_version({"paypal_sdk_version": "v6", "detected_sdk_version": "v5"}) == "v6"
    cart_with_only_message = _scanner_page("cart", "desktop", 200, category="messaging")
    issues = _rules({"detected_sdk_version": "v6", "pages": [cart_with_only_message]})
    assert "no_paypal_on_cart" in {i["issue_id"] for i in issues}


def test_visible_without_scroll_from_bounding_box():
    page = {"viewport": "mobile"}
    assert is_visible_without_scroll({"bounding_box": {"y": 300, "height": 45}}, page)
    assert not is_visible_without_scroll({"bounding_box": {"y": 1339, "height": 45}}, page)
    assert not is_visible_without_scroll({"visible": False, "bounding_box": {"y": 10, "height": 45}}, page)
    assert is_visible_without_scroll({"bounding_box": {"y": 700, "height": 45}}, {"viewport_height": 844})
    assert is_visible_without_scroll({"visible_without_scroll": True}, page)
