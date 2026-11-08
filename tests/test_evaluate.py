"""Tests for the AI engine evaluation tool (Member 4). Run with: pytest tests/test_evaluate.py -v"""

import json

from ai_engine import evaluate
from ai_engine.evaluate import build_rule_cases, evaluate_rules, precision_recall, to_markdown


def test_builds_all_combinations_plus_edge_cases():
    cases = build_rule_cases()
    assert len(cases) == 4 * 2 * 2 * 3 + len(evaluate.build_edge_cases())
    assert len({case["name"] for case in cases}) == len(cases)


def test_rules_score_perfectly_on_labelled_cases():
    result = evaluate_rules()
    assert result["mismatches"] == []
    assert result["exact_match_rate"] == 1.0
    assert result["deterministic"] and result["high_issues_ranked_first"]
    for metrics in result["per_issue"].values():
        assert metrics["precision"] == 1.0 and metrics["recall"] == 1.0


def test_evaluation_catches_a_wrong_label():
    case = build_rule_cases()[0]
    case["expected"] = set()  # deliberately wrong
    result = evaluate_rules([case])
    assert result["exact_matches"] == 0 and len(result["mismatches"]) == 1


def test_precision_recall_math():
    table = precision_recall([({"a"}, {"a"}), ({"a"}, set()), (set(), {"a"})], ("a",))
    assert table["a"]["precision"] == 0.5 and table["a"]["recall"] == 0.5


def test_markdown_contains_table():
    text = to_markdown(evaluate_rules())
    assert "| `sdk_outdated` | 100% | 100% |" in text
    assert "not measurements on real stores" in text


def test_vision_evaluation_with_fake_model(tmp_path, monkeypatch):
    image = tmp_path / "cart.png"
    image.write_bytes(b"png")
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(json.dumps([
        {"image": "cart.png", "label": "cart (desktop)", "expected": ["no_paypal_on_cart"]},
        {"image": "missing.png", "label": "cart (desktop)", "expected": []},
    ]))
    fake_issue = {"issue_id": "no_paypal_on_cart", "severity": "high"}
    monkeypatch.setattr("ai_engine.vision.run_vision_checks", lambda scan, call_model=None: ([fake_issue], []))
    result = evaluate.evaluate_vision(str(cases_file))
    assert result["evaluated"] == 1 and result["exact_matches"] == 1
    assert result["errors"] == ["missing.png: file not found"]


def test_main_writes_markdown(tmp_path, capsys):
    out = tmp_path / "results.md"
    assert evaluate.main(["--markdown", str(out)]) == 0
    assert "AI engine evaluation" in out.read_text()


def test_answer_key_uses_only_known_issue_ids():
    from ai_engine.capture_eval_shots import ANSWER_KEY
    from ai_engine.prompts import VISION_ISSUE_CATALOGUE
    assert len(ANSWER_KEY) == 8
    for store, step, viewport, _needs, expected, _why in ANSWER_KEY:
        assert store in ("legacy", "upgraded") and step in ("cart", "checkout")
        assert viewport in ("desktop", "mobile")
        assert set(expected) <= set(VISION_ISSUE_CATALOGUE)


def test_capture_skips_pages_where_paypal_cannot_load(tmp_path):
    """No internet to PayPal here: cart pages without PayPal are still captured, the rest skipped."""
    from ai_engine.capture_eval_shots import capture
    summary = capture(tmp_path, paypal_wait=2)
    cases = json.loads((tmp_path / "eval_cases.json").read_text())
    captured = {case["image"] for case in cases}
    assert {"legacy_cart_desktop.png", "legacy_cart_mobile.png"} <= captured
    assert summary["captured"] + len(summary["skipped"]) == 8
    for case in cases:
        assert (tmp_path / case["image"]).is_file() and case["label"] in (
            "cart (desktop)", "cart (mobile)", "checkout (desktop)", "checkout (mobile)")
