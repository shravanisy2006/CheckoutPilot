"""
Capture labelled screenshots of the two demo stores for the vision evaluation.

From the project root (venv active):
    python -m ai_engine.capture_eval_shots
    python -m ai_engine.evaluate --vision-cases outputs/eval_shots/eval_cases.json --markdown docs/ai_results.md

It starts both demo stores (if not already running), adds the pen to the cart,
and screenshots the cart and checkout pages on desktop and mobile - only what is
visible WITHOUT scrolling, like a shopper's first view. Every screenshot gets the
correct answer ("expected" issues), which we know because we built the stores.

Screenshots go to outputs/eval_shots/ (not committed to git).
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

OUT_DIR = Path("outputs/eval_shots")
PAYPAL_WAIT_SECONDS = 25

VIEWPORTS = {
    "desktop": {"viewport": {"width": 1280, "height": 900}, "device_scale_factor": 1},
    "mobile": {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2,
               "is_mobile": True, "has_touch": True},
}

# The answer key. We built both stores, so we know exactly what is on each page.
# Only issues the vision model is allowed to report (VISION_ISSUE_CATALOGUE) appear here.
ANSWER_KEY = [
    # store,     page,       viewport,  PayPal should render?, expected issues, why
    ("legacy",   "cart",     "desktop", False, ["no_paypal_on_cart"], "Legacy cart has no PayPal button."),
    ("legacy",   "cart",     "mobile",  False, ["no_paypal_on_cart"], "Legacy cart has no PayPal button."),
    ("legacy",   "checkout", "desktop", True,  [], "PayPal is visible next to the order summary."),
    ("legacy",   "checkout", "mobile",  True,  ["button_below_fold_mobile"],
     "PayPal sits under a long form; not visible without scrolling."),
    ("upgraded", "cart",     "desktop", True,  [], "PayPal express button under the cart total."),
    ("upgraded", "cart",     "mobile",  True,  [], "PayPal express button visible on the phone screen."),
    ("upgraded", "checkout", "desktop", True,  [], "PayPal visible in the order summary."),
    ("upgraded", "checkout", "mobile",  True,  [], "Summary + PayPal come before the form on mobile."),
]


def _store_url(name: str) -> str:
    from demo_stores.serve import KNOWN_STORES
    return f"http://localhost:{KNOWN_STORES[name][1]}"


def _running(url: str) -> bool:
    try:
        return requests.get(f"{url}/health", timeout=2).status_code == 200
    except requests.RequestException:
        return False


def _paypal_rendered(page, timeout: float) -> bool:
    """True once a real PayPal button (v5 iframe or v6 <paypal-button>) is drawn."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.locator("#paypal-button-container paypal-button:not([hidden])").count():
            return True
        frame = page.locator("#paypal-button-container iframe").first
        if frame.count():
            box = frame.bounding_box()
            if box and box["height"] > 20:
                page.wait_for_timeout(1500)  # let the button finish painting
                return True
        page.wait_for_timeout(500)
    return False


def capture(out_dir: Path = OUT_DIR, paypal_wait: float = PAYPAL_WAIT_SECONDS) -> dict:
    """Take all screenshots and write eval_cases.json. Returns a summary dict."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    from demo_stores.serve import resolve_store, start_store, stop_store

    out_dir.mkdir(parents=True, exist_ok=True)
    started, cases, skipped = [], [], []
    try:
        for name in ("legacy", "upgraded"):
            url = _store_url(name)
            if not _running(url):
                store_dir, port = resolve_store(name)
                start_store(store_dir, port)
                started.append(port)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for store, step, viewport, needs_paypal, expected, why in ANSWER_KEY:
                context = browser.new_context(locale="en-US", **VIEWPORTS[viewport])
                page = context.new_page()
                url = _store_url(store)
                page.goto(url + "/", wait_until="domcontentloaded")
                page.click("#add-to-cart")
                page.goto(f"{url}/{step}", wait_until="load")
                try:
                    # PayPal's scripts can keep the network busy for a long time; don't wait forever.
                    page.wait_for_load_state("networkidle", timeout=5000)
                except PlaywrightTimeout:
                    pass
                image = f"{store}_{step}_{viewport}.png"
                if needs_paypal and not _paypal_rendered(page, paypal_wait):
                    skipped.append(f"{image}: PayPal button did not load (check internet / PAYPAL_CLIENT_ID)")
                    context.close()
                    continue
                page.wait_for_timeout(500)
                page.screenshot(path=str(out_dir / image), full_page=False)
                cases.append({"image": image, "label": f"{step} ({viewport})",
                              "expected": expected, "why": why})
                context.close()
            browser.close()
    finally:
        for port in started:
            stop_store(port)

    cases_file = out_dir / "eval_cases.json"
    cases_file.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    return {"cases_file": str(cases_file), "captured": len(cases), "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture labelled demo-store screenshots for the vision evaluation.")
    parser.add_argument("--out", default=str(OUT_DIR), help="folder for screenshots (default outputs/eval_shots)")
    args = parser.parse_args(argv)
    print("Capturing screenshots of both demo stores (about 1 minute) ...")
    summary = capture(Path(args.out))
    print(f"Captured {summary['captured']} of {len(ANSWER_KEY)} screenshots -> {summary['cases_file']}")
    for line in summary["skipped"]:
        print(f"  Skipped {line}")
    if summary["captured"]:
        print("\nNext:\n  python -m ai_engine.evaluate --vision-cases "
              f"{summary['cases_file']} --markdown docs/ai_results.md")
    return 0 if summary["captured"] == len(ANSWER_KEY) else 1


if __name__ == "__main__":
    sys.exit(main())
