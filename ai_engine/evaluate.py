"""
Measure how well the AI engine and ranker work, and print results for the README.

Usage (from the project root, with the venv active):

    python -m ai_engine.evaluate                       # rule checks + ranking (no API calls)
    python -m ai_engine.evaluate --vision-cases eval_cases.json   # also test the vision AI
    python -m ai_engine.evaluate --markdown results.md # also save the tables to a file

1. Rule evaluation
   Builds labelled test scans covering every combination of:
     SDK version (v4, v5, v6, none) x PayPal on product page (yes/no)
     x PayPal on cart (yes/no) x mobile checkout button (visible / below fold / absent)
   plus edge cases (missing pages, mixed visibility, empty scan).
   The expected issues for each scan come from the scenario description, not
   from the rule code, so the evaluation can catch rule mistakes.
   NOTE: these are synthetic scans. They test detection logic, not real stores.

2. Vision evaluation (optional, uses the AI API)
   A JSON file listing screenshots you labelled yourself:
     [{"image": "shots/legacy_cart.png", "label": "cart (desktop)",
       "expected": ["no_paypal_on_cart"]}, ...]
   Each image is sent to the vision model and its answer compared with "expected".
"""

import argparse
import copy
import itertools
import json
import sys
import time
from pathlib import Path

from ai_engine.errors import ModuleError
from ai_engine.prompts import VISION_ISSUE_CATALOGUE
from ai_engine.rules import run_rule_checks
from impact_ranker import health_score, rank_issues

RULE_ISSUES = ("sdk_outdated", "no_paypal_on_cart", "no_paypal_on_product", "button_below_fold_mobile")
SDK_SCRIPTS = {
    "v4": "https://www.paypalobjects.com/api/checkout.js",
    "v5": "https://www.paypal.com/sdk/js?client-id=TEST",
    "v6": "https://www.sandbox.paypal.com/web-sdk/v6/core",
    "none": None,
}


# ---------------------------------------------------------------------------
# Building labelled test scans
# ---------------------------------------------------------------------------
def _button(visible: bool) -> dict:
    return {"type": "button", "x": 40, "y": 400 if visible else 1300, "width": 300,
            "height": 45, "visible_without_scroll": visible}


def _page(step: str, viewport: str, sdk: str, elements: list[dict]) -> dict:
    script = SDK_SCRIPTS[sdk]
    return {
        "step": step, "viewport": viewport, "url": f"http://store.test/{step}",
        "screenshot_path": "", "scripts": [script] if script else [],
        "paypal_elements": elements, "viewport_height": 844 if viewport == "mobile" else 900,
    }


def build_scenario(sdk: str, product_paypal: bool, cart_paypal: bool, mobile_button: str) -> dict:
    """
    Build one labelled case.

    mobile_button: "visible", "below_fold" or "absent" (on the mobile checkout page).
    Returns {"name", "scan_data", "expected": set of issue_ids}.
    """
    pages = []
    for viewport in ("desktop", "mobile"):
        pages.append(_page("product", viewport, sdk, [_button(True)] if product_paypal else []))
        pages.append(_page("cart", viewport, sdk, [_button(True)] if cart_paypal else []))
        if viewport == "desktop":
            checkout = [_button(True)]
        else:
            checkout = {"visible": [_button(True)], "below_fold": [_button(False)], "absent": []}[mobile_button]
        pages.append(_page("checkout", viewport, sdk, checkout))

    expected = set()
    if sdk in ("v4", "v5"):
        expected.add("sdk_outdated")
    if not cart_paypal:
        expected.add("no_paypal_on_cart")
    if not product_paypal:
        expected.add("no_paypal_on_product")
    if mobile_button == "below_fold":
        expected.add("button_below_fold_mobile")

    name = f"sdk={sdk} product={'Y' if product_paypal else 'N'} cart={'Y' if cart_paypal else 'N'} mobile={mobile_button}"
    scan = {"scan_id": name, "store_url": "http://store.test", "pages": pages,
            "paypal_sdk_version": sdk, "warnings": []}
    return {"name": name, "scan_data": scan, "expected": expected}


def build_edge_cases() -> list[dict]:
    """Cases where the scanner returned partial data."""
    cases = []

    empty = {"scan_id": "empty", "store_url": "x", "pages": [], "paypal_sdk_version": "none", "warnings": []}
    cases.append({"name": "edge: empty scan", "scan_data": empty, "expected": set()})

    no_cart = build_scenario("v6", True, False, "visible")
    no_cart["scan_data"]["pages"] = [p for p in no_cart["scan_data"]["pages"] if p["step"] != "cart"]
    no_cart.update(name="edge: cart page missing (scanner could not reach it)", expected=set())
    cases.append(no_cart)

    mixed = build_scenario("v6", True, True, "below_fold")
    for page in mixed["scan_data"]["pages"]:
        if page["step"] == "checkout" and page["viewport"] == "mobile":
            page["paypal_elements"] = [_button(False), _button(True)]
    mixed.update(name="edge: two mobile buttons, one visible", expected=set())
    cases.append(mixed)

    cart_desktop_only = build_scenario("v6", True, True, "visible")
    for page in cart_desktop_only["scan_data"]["pages"]:
        if page["step"] == "cart" and page["viewport"] == "mobile":
            page["paypal_elements"] = []
    cart_desktop_only.update(name="edge: PayPal on desktop cart only", expected=set())
    cases.append(cart_desktop_only)

    no_version = build_scenario("v5", True, True, "visible")
    del no_version["scan_data"]["paypal_sdk_version"]
    no_version.update(name="edge: SDK version missing from scan", expected=set())
    cases.append(no_version)
    return cases


def build_rule_cases() -> list[dict]:
    """All combinations plus edge cases."""
    combos = itertools.product(("v4", "v5", "v6", "none"), (True, False), (True, False),
                               ("visible", "below_fold", "absent"))
    return [build_scenario(*combo) for combo in combos] + build_edge_cases()


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def precision_recall(results: list[tuple[set, set]], issue_ids: tuple[str, ...]) -> dict:
    """
    Per-issue precision and recall from (expected, found) pairs.

    precision = of the times we reported the issue, how often it was real
    recall    = of the times the issue was real, how often we reported it
    """
    table = {}
    for issue_id in issue_ids:
        tp = sum(1 for exp, got in results if issue_id in exp and issue_id in got)
        fp = sum(1 for exp, got in results if issue_id not in exp and issue_id in got)
        fn = sum(1 for exp, got in results if issue_id in exp and issue_id not in got)
        table[issue_id] = {
            "true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
        }
    return table


def evaluate_rules(cases: list[dict] | None = None, repeats: int = 3) -> dict:
    """Run rule checks + ranking on labelled cases and compute metrics."""
    cases = cases if cases is not None else build_rule_cases()
    results, mismatches, timings = [], [], []
    deterministic = True
    ranking_ok = True

    for case in cases:
        start = time.perf_counter()
        issues = run_rule_checks(copy.deepcopy(case["scan_data"]))
        ranked = rank_issues(issues)
        health_score(ranked)
        timings.append(time.perf_counter() - start)

        found = {issue["issue_id"] for issue in issues}
        results.append((case["expected"], found))
        if found != case["expected"]:
            mismatches.append({"case": case["name"], "expected": sorted(case["expected"]), "found": sorted(found)})

        for _ in range(repeats - 1):  # same input must always give the same ranked output
            if rank_issues(run_rule_checks(copy.deepcopy(case["scan_data"]))) != ranked:
                deterministic = False

        has_high = any(issue["severity"] == "high" for issue in issues)
        if has_high and ranked[0]["severity"] != "high":  # a high issue must always rank first
            ranking_ok = False

    exact = sum(1 for exp, got in results if exp == got)
    return {
        "cases": len(cases),
        "exact_matches": exact,
        "exact_match_rate": exact / len(cases) if cases else None,
        "per_issue": precision_recall(results, RULE_ISSUES),
        "deterministic": deterministic,
        "high_issues_ranked_first": ranking_ok,
        "avg_ms_per_scan": 1000 * sum(timings) / len(timings) if timings else 0.0,
        "mismatches": mismatches,
    }


def evaluate_vision(cases_file: str) -> dict:
    """Send each labelled screenshot to the vision model and compare with expectations."""
    from ai_engine.try_vision import build_scan_data
    from ai_engine.vision import run_vision_checks

    base = Path(cases_file).resolve().parent
    cases = json.loads(Path(cases_file).read_text(encoding="utf-8"))
    results, details, errors, timings = [], [], [], []

    for number, case in enumerate(cases, 1):
        image = (base / case["image"]).resolve()
        expected = set(case.get("expected", []))
        if not image.is_file():
            errors.append(f"{case['image']}: file not found")
            continue
        print(f"[{number}/{len(cases)}] {case['image']} ...", end=" ", flush=True)
        start = time.perf_counter()
        try:
            issues, _ = run_vision_checks(build_scan_data([str(image)], [case.get("label", "")]))
        except ModuleError as error:
            print(f"error {error.code} ({time.perf_counter() - start:.0f}s)", flush=True)
            errors.append(f"{case['image']}: {error.code}")
            continue
        timings.append(time.perf_counter() - start)
        print(f"done in {timings[-1]:.0f}s", flush=True)
        found = {issue["issue_id"] for issue in issues}
        results.append((expected, found))
        details.append({"image": case["image"], "expected": sorted(expected), "found": sorted(found)})

    issue_ids = tuple(sorted({i for exp, got in results for i in exp | got} & set(VISION_ISSUE_CATALOGUE)))
    exact = sum(1 for exp, got in results if exp == got)
    return {
        "cases": len(cases),
        "evaluated": len(results),
        "exact_matches": exact,
        "exact_match_rate": exact / len(results) if results else None,
        "per_issue": precision_recall(results, issue_ids),
        "avg_seconds_per_image": sum(timings) / len(timings) if timings else None,
        "details": details,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def to_markdown(rules: dict, vision: dict | None = None) -> str:
    """Format results as Markdown tables for the README."""
    lines = [
        "### AI engine evaluation",
        "",
        f"**Rule checks** on {rules['cases']} labelled synthetic scans "
        "(every combination of SDK version, PayPal placement and mobile layout, plus scanner edge cases):",
        "",
        "| Issue | Precision | Recall | Correct detections | False alarms | Missed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for issue_id, m in rules["per_issue"].items():
        lines.append(f"| `{issue_id}` | {_pct(m['precision'])} | {_pct(m['recall'])} | "
                     f"{m['true_positives']} | {m['false_positives']} | {m['false_negatives']} |")
    lines += [
        "",
        f"- Scans where every issue was exactly right: **{rules['exact_matches']}/{rules['cases']} "
        f"({_pct(rules['exact_match_rate'])})**",
        f"- Same input gives the same ranking every run: **{'yes' if rules['deterministic'] else 'NO'}**",
        f"- High-severity issues always ranked first: **{'yes' if rules['high_issues_ranked_first'] else 'NO'}**",
        f"- Average time per scan (rules + ranking): **{rules['avg_ms_per_scan']:.2f} ms**",
        "",
        "_Synthetic scans test the detection logic; they are not measurements on real stores._",
    ]
    if vision:
        lines += [
            "",
            f"**Vision model** on {vision['evaluated']} hand-labelled screenshots:",
            "",
            "| Issue | Precision | Recall | Correct | False alarms | Missed |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for issue_id, m in vision["per_issue"].items():
            lines.append(f"| `{issue_id}` | {_pct(m['precision'])} | {_pct(m['recall'])} | "
                         f"{m['true_positives']} | {m['false_positives']} | {m['false_negatives']} |")
        lines += [
            "",
            f"- Screenshots where every issue was exactly right: **{vision['exact_matches']}/{vision['evaluated']} "
            f"({_pct(vision['exact_match_rate'])})**",
        ]
        if vision["avg_seconds_per_image"] is not None:
            lines.append(f"- Average vision time per screenshot: **{vision['avg_seconds_per_image']:.1f} s**")
        if vision["errors"]:
            lines.append(f"- Not evaluated (errors): {len(vision['errors'])}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the CheckoutPilot AI engine.")
    parser.add_argument("--vision-cases", help="JSON file of labelled screenshots (uses the AI API)")
    parser.add_argument("--markdown", help="Also save the results tables to this Markdown file")
    args = parser.parse_args(argv)

    rules = evaluate_rules()
    vision = evaluate_vision(args.vision_cases) if args.vision_cases else None
    report = to_markdown(rules, vision)
    print(report)

    for mismatch in rules["mismatches"]:
        print(f"Rule mismatch - {mismatch['case']}: expected {mismatch['expected']}, found {mismatch['found']}")
    if vision:
        for detail in vision["details"]:
            if detail["expected"] != detail["found"]:
                print(f"Vision mismatch - {detail['image']}: expected {detail['expected']}, found {detail['found']}")
        for error in vision["errors"]:
            print(f"Vision error - {error}")

    if args.markdown:
        Path(args.markdown).write_text(report, encoding="utf-8")
        print(f"Saved to {args.markdown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
