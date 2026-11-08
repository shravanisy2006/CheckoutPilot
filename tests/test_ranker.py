"""
Tests for the impact ranker (Member 4).

Run with:  pytest tests/test_ranker.py -v
"""

import copy
import json
import random
from pathlib import Path

from ai_engine.rules import run_rule_checks
from impact_ranker import health_score, rank_gaps, rank_issues, score_issue

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def legacy_issues() -> list[dict]:
    return run_rule_checks(load("scan_data_legacy.json"))


def test_score_formula():
    assert score_issue({"severity": "high", "category": "sdk"}) == 100
    assert score_issue({"severity": "high", "category": "presentment"}) == 90
    assert score_issue({"severity": "medium", "category": "mobile"}) == 47     # 2 x 0.7 / 3
    assert score_issue({"severity": "low", "category": "messaging"}) == 17     # 1 x 0.5 / 3
    assert score_issue({"severity": "high", "category": "sdk", "confidence": 0.5}) == 50


def test_unknown_values_get_safe_defaults():
    assert score_issue({}) == 17                                   # low x default 0.5
    assert score_issue({"severity": "high", "category": "sdk", "confidence": "bad"}) == 100
    assert score_issue({"severity": "high", "category": "sdk", "confidence": 9}) == 100


def test_legacy_ranking_order():
    ranked = rank_issues(legacy_issues())
    assert [r["issue_id"] for r in ranked][:2] == ["sdk_outdated", "no_paypal_on_cart"]
    assert [r["impact"]["rank"] for r in ranked] == list(range(1, len(ranked) + 1))
    scores = [r["impact"]["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_ranked_issue_shape():
    for item in rank_issues(legacy_issues()):
        impact = item["impact"]
        assert {"issue_id", "score", "rank", "rationale", "assumption", "assumption_source"} <= set(impact)
        assert impact["issue_id"] == item["issue_id"]
        assert 0 <= impact["score"] <= 100


def test_every_assumption_names_source_and_is_not_a_measurement():
    for item in rank_issues(legacy_issues()):
        assumption = item["impact"]["assumption"]
        assert item["impact"]["assumption_source"] in assumption
        assert "not measured for this store" in assumption


def test_ranking_is_deterministic_and_order_independent():
    issues = legacy_issues()
    expected = rank_issues(copy.deepcopy(issues))
    for seed in range(3):
        shuffled = copy.deepcopy(issues)
        random.Random(seed).shuffle(shuffled)
        assert rank_issues(shuffled) == expected


def test_rank_issues_does_not_modify_input():
    issues = legacy_issues()
    before = copy.deepcopy(issues)
    rank_issues(issues)
    assert issues == before


def test_health_scores():
    legacy = health_score(rank_issues(legacy_issues()))
    upgraded = health_score(rank_issues(run_rule_checks(load("scan_data_upgraded.json"))))
    assert health_score([]) == 100
    assert 0 <= legacy < upgraded <= 100
    assert legacy == 21    # 100 - (0.40x100 + 0.25x90 + 0.15x60 + 0.15x47)


def test_health_score_clamped_at_zero():
    many = [{"issue_id": f"i{n}", "severity": "high", "category": "sdk"} for n in range(20)]
    assert health_score(rank_issues(many)) == 0


def test_empty_input():
    assert rank_issues([]) == []


def test_rank_gaps_compatibility_with_old_backend():
    ranked = rank_gaps([{"gap_id": "sdk_v5", "title": "Old SDK"}])
    assert ranked[0]["gap_id"] == "sdk_v5"
    assert "estimated_impact" in ranked[0]
