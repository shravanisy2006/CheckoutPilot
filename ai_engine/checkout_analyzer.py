"""
AI-powered checkout analysis.

Two kinds of checks will live here:
  1. Rule-based checks for simple facts (which PayPal SDK version is loaded,
     whether a PayPal button exists on a page).
  2. Vision-model checks for judgement calls on screenshots (is the PayPal
     button prominent or buried? is the mobile layout cramped?).

Input: the dictionary returned by scanner.scan_store().
Output: a list of gap dictionaries (see `analyze_checkout`).

STATUS: placeholder only. No AI calls yet.
"""


def analyze_checkout(scan_data: dict) -> list[dict]:
    """
    Detect checkout gaps from raw scan data.

    Args:
        scan_data: Output of scanner.scan_store().

    Returns:
        A list of gaps, each shaped like:
        {
            "gap_id": str,        # e.g. "sdk_v5"
            "title": str,
            "severity": str,      # "high" | "medium" | "low"
            "description": str,
        }
    """
    gaps: list[dict] = []
    gaps.extend(run_rule_checks(scan_data))
    gaps.extend(run_vision_checks(scan_data))
    return gaps


def run_rule_checks(scan_data: dict) -> list[dict]:
    """
    Simple, deterministic checks that don't need AI.

    TODO: detect PayPal SDK version (v4 checkout.js / v5 / v6) from script URLs.
    TODO: check whether a PayPal button appears on product, cart and checkout pages.
    TODO: check for Pay Later messaging components.
    """
    return []


def run_vision_checks(scan_data: dict) -> list[dict]:
    """
    Send screenshots to a vision-capable AI model and ask for structured JSON.

    TODO: choose the AI provider (see AI_PROVIDER in .env).
    TODO: write the prompt asking whether the PayPal button is prominent.
    TODO: parse the model's JSON answer into gap dictionaries.
    """
    return []
