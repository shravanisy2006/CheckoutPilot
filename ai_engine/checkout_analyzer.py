"""
AI-powered checkout analysis: the AI engine's main entry point.

Combines two kinds of checks:
  1. Rule checks (ai_engine/rules.py)  - deterministic facts, always run.
  2. Vision checks (ai_engine/vision.py) - AI judgement on screenshots.

If the vision step fails (no key, network error, bad output twice), the rule
issues are still returned and a warning explains what happened.

Functions:
    analyze_checkout(scan_data)          -> list of CheckoutIssue dicts (team contract)
    analyze_checkout_detailed(scan_data) -> {"issues": [...], "warnings": [...]}
"""

import os

from ai_engine.errors import ModuleError
from ai_engine.rules import run_rule_checks
from ai_engine.vision import ModelCaller, run_vision_checks

SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}


def _vision_enabled() -> bool:
    """Vision can be switched off with AI_VISION_ENABLED=false in .env."""
    return os.getenv("AI_VISION_ENABLED", "true").strip().lower() not in ("false", "0", "no")


def merge_issues(rule_issues: list[dict], vision_issues: list[dict]) -> list[dict]:
    """
    Combine rule and vision issues, removing duplicates by issue_id.

    When both find the same issue, the rule version is kept (it is
    deterministic), its severity becomes the higher of the two, and the
    evidence notes that the vision model agreed.
    """
    merged: dict[str, dict] = {}
    for issue in rule_issues:
        merged.setdefault(issue["issue_id"], dict(issue))

    for issue in vision_issues:
        existing = merged.get(issue["issue_id"])
        if existing is None:
            merged[issue["issue_id"]] = dict(issue)
            continue
        if SEVERITY_ORDER.get(issue["severity"], 0) > SEVERITY_ORDER.get(existing["severity"], 0):
            existing["severity"] = issue["severity"]
        existing["source"] = "rule+vision"
        existing["evidence"] = existing["evidence"].rstrip(".") + ". Also confirmed by the vision model."

    return list(merged.values())


def analyze_checkout_detailed(scan_data: dict, call_model: ModelCaller | None = None) -> dict:
    """
    Detect checkout issues and report any warnings.

    Args:
        scan_data: ScanData from the scanner.
        call_model: Optional replacement for the AI call (used by tests).

    Returns:
        {"issues": [CheckoutIssue, ...], "warnings": ["CODE: message", ...]}
    """
    warnings: list[str] = []
    rule_issues = run_rule_checks(scan_data)
    vision_issues: list[dict] = []

    if _vision_enabled():
        try:
            vision_issues, vision_warnings = run_vision_checks(scan_data, call_model)
            warnings.extend(vision_warnings)
        except ModuleError as error:
            warnings.append(f"{error.code}: {error.message} Showing rule-based issues only.")
        except Exception as error:  # never let the AI step crash the scan
            warnings.append(f"AI_UNAVAILABLE: Unexpected vision error ({error}). Showing rule-based issues only.")

    return {"issues": merge_issues(rule_issues, vision_issues), "warnings": warnings}


def analyze_checkout(scan_data: dict) -> list[dict]:
    """
    Team contract: detect checkout issues from ScanData.

    Returns only the issue list. Warnings are also appended to
    scan_data["warnings"] so the backend can show them. Use
    analyze_checkout_detailed() to get warnings separately.
    """
    result = analyze_checkout_detailed(scan_data)
    if result["warnings"]:
        scan_data.setdefault("warnings", []).extend(result["warnings"])
    return result["issues"]
