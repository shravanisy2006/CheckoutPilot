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
