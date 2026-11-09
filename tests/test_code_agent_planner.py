"""
Tests for the traceable upgrade planner.
"""

from code_agent.planner import UpgradePlanner, plan_upgrades
from code_agent.upgrade_agent import create_upgrade_plan


def test_empty_gaps_contract():
    """Verify that explicitly passing empty gaps returns an empty plan (team contract)."""
    assert create_upgrade_plan(".", []) == []
    assert plan_upgrades("demo_stores/legacy_store", []) == []


def test_plan_legacy_store_gaps():
    """Verify planner creates detailed, traceable changes for legacy store flaws."""
    gaps = [
        {"gap_id": "sdk_outdated", "title": "Outdated SDK"},
        {"gap_id": "no_paypal_on_cart", "title": "No PayPal on Cart"},
        {"gap_id": "button_below_fold_mobile", "title": "Button Below Fold on Mobile"},
    ]

    plan = plan_upgrades("demo_stores/legacy_store", gaps)
    assert len(plan) >= 3

    gap_ids = [change["gap_id"] for change in plan]
    assert "sdk_outdated" in gap_ids
    assert "no_paypal_on_cart" in gap_ids
    assert "button_below_fold_mobile" in gap_ids

    # Check that each change contains full traceability fields
    for change in plan:
        for field in (
            "gap_id",
            "file",
            "target_file",
            "change_summary",
            "line_start",
            "line_end",
            "action",
            "before_snippet",
            "after_snippet",
            "rationale",
            "estimated_impact",
            "syntax_type",
            "priority",
        ):
            assert field in change, f"Missing field {field} in planned change"

        assert len(change["rationale"]) > 20
        assert len(change["estimated_impact"]) > 10


def test_plan_technical_rationale_content():
    """Verify rationales cite PayPal v6 SDK, web components, and client-tokens."""
    gaps = [{"gap_id": "sdk_outdated"}]
    plan = plan_upgrades("demo_stores/legacy_store", gaps)

    sdk_changes = [c for c in plan if c["gap_id"] == "sdk_outdated"]
    assert len(sdk_changes) >= 1

    # At least one change targets checkout.html and one targets app.py
    files_targeted = [c["file"] for c in sdk_changes]
    assert any("checkout.html" in f for f in files_targeted)
    assert any("app.py" in f for f in files_targeted)

    # Check rationale mentions v6
    assert any("v6" in c["rationale"] for c in sdk_changes)
