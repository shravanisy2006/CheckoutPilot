"""
A plain-language summary of a scan for the store owner (not a developer).

    from ai_engine.summary import summarize_for_owner
    summary = summarize_for_owner(scan_result)   # {"text": "...", "generated_by": "ai" | "template"}

Gemini (or the provider in .env) writes at most 3 short sentences from the scan's own findings.
Guardrails: the model only sees the findings (no page content), may not invent money or
percentages, and its answer is checked; anything off falls back to a template summary, labelled
"template" so the dashboard never claims the AI wrote it.
"""

import hashlib
import json
import os
import re

from ai_engine.errors import ModuleError

MAX_CHARS = 600
_cache: dict[str, dict] = {}

SYSTEM = (
    "You explain website checkout audits to small online-store owners who are not technical. "
    "Write plainly and kindly, like a helpful consultant."
)

PROMPT = """Here is the result of an audit of an online store's PayPal checkout, as JSON:

{facts}

Write a summary for the store owner in AT MOST 3 short sentences (under 70 words in total):
1. how healthy the checkout is overall,
2. the most important problem and what it means for a shopper,
3. what to do first.
Rules: use only the facts above; plain words (say "PayPal button", not "SDK" alone; explain "v5/v6" as
"an older/newer version of PayPal's code"); no money amounts, no percentages, no promises of more
sales; no markdown, no lists, no greeting. Reply with the summary text only."""


def _facts(scan: dict) -> dict:
    issues = sorted(scan.get("issues") or [], key=lambda i: i.get("priority") or i.get("rank") or 99)
    return {
        "health_score_out_of_100": scan.get("health_score"),
        "health_label": scan.get("health_label", ""),
        "paypal_code_version": scan.get("paypal_sdk_version", ""),
        "issues_in_priority_order": [
            {"title": i.get("title", ""), "severity": i.get("severity", ""), "where": i.get("surface", "")}
            for i in issues[:5]
        ],
    }


def template_summary(scan: dict) -> str:
    """A clear summary without AI (also the fallback)."""
    score = scan.get("health_score")
    issues = sorted(scan.get("issues") or [], key=lambda i: i.get("priority") or i.get("rank") or 99)
    if not issues:
        return (f"Your PayPal checkout looks healthy ({score}/100). We found no problems on the pages we could "
                "check. Keep an eye on it after each change to your store.")
    label = scan.get("health_label") or ("poor" if (score or 0) < 50 else "fair" if (score or 0) < 80 else "good")
    top = issues[0]
    more = f" and {len(issues) - 1} smaller issue{'s' if len(issues) > 2 else ''}" if len(issues) > 1 else ""
    first = top.get("title", "the first issue").rstrip(".")
    return (f"Your PayPal checkout scores {score}/100 ({label}). The biggest problem is: {first}{more}. "
            f"Start with that fix first: CheckoutPilot can write it for you and test it with a PayPal Sandbox payment.")


def _summary_enabled() -> bool:
    default = os.getenv("AI_VISION_ENABLED", "true")
    return os.getenv("AI_SUMMARY_ENABLED", default).strip().lower() not in ("false", "0", "no")


def _acceptable(text: str, scan: dict) -> bool:
    """Reject answers that break the rules (too long, money/percent, markdown, invented numbers)."""
    if not text or len(text) > MAX_CHARS or len(re.findall(r"[.!?](\s|$)", text)) > 4:
        return False
    if re.search(r"[$€£₹%]|\bpercent\b|\b\d+\s?x\b", text, re.IGNORECASE):
        return False
    if re.search(r"^\s*[-*#]|\*\*", text, re.MULTILINE):
        return False
    allowed = {str(scan.get("health_score")), "100", "5", "6", "1", "2", "3"}
    numbers = set(re.findall(r"\d+", text))
    return numbers <= allowed


def summarize_for_owner(scan: dict, call_model=None) -> dict:
    """{"text": ..., "generated_by": "ai" | "template"}; never raises."""
    fallback = {"text": template_summary(scan), "generated_by": "template"}
    if call_model is None and not _summary_enabled():
        return fallback
    facts = _facts(scan)
    key = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()
    if call_model is None and key in _cache:
        return _cache[key]
    try:
        if call_model is None:
            from ai_engine.vision import get_default_caller
            call_model = get_default_caller()
        text = " ".join(call_model(SYSTEM, PROMPT.format(facts=json.dumps(facts, indent=2)), []).split())
    except (ModuleError, Exception):  # no key, network, provider error: the template is fine
        return fallback
    result = {"text": text, "generated_by": "ai"} if _acceptable(text, scan) else fallback
    _cache[key] = result
    return result
