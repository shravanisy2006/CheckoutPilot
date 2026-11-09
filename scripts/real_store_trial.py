"""
Real-store trial: scan a list of public stores and see which ones work well for the demo.

From the project root (venv active):
    python -m scripts.real_store_trial https://demo.paypal.com/us/demo/home https://shop.example.com
    python -m scripts.real_store_trial --file stores.txt          # one URL per line, # for comments
    python -m scripts.real_store_trial --file stores.txt --no-vision

For each store it runs the real pipeline (scanner -> AI engine -> impact ranker) and
prints one row: which pages it reached, the PayPal SDK version, the issues found and
the health score. Results, screenshots and a Markdown summary are saved under
outputs/real_store_trials/<run>/ (git-ignored: never commit other companies' screenshots).

Be a polite visitor: public pages only, one scan per store, a pause between stores.
Nothing is bought and no login is used. The sandbox verifier is NOT run here (it only
ever pays on local demo stores).
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

OUT_ROOT = Path("outputs/real_store_trials")
PAUSE_BETWEEN_STORES_SECONDS = 5
STEPS = ("product", "cart", "checkout")
STEP_LETTER = {"product": "P", "cart": "C", "checkout": "K"}


def read_urls(args) -> list[str]:
    urls = list(args.urls)
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                urls.append(line)
    seen, unique = set(), []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", url.lower().split("//", 1)[-1]).strip("_")[:60] or "store"


def pages_reached(scan: dict) -> dict:
    """{"desktop": {"product": True, ...}, "mobile": {...}} from the scanner's pages."""
    reached = {"desktop": {}, "mobile": {}}
    for page in scan.get("pages") or []:
        viewport = page.get("viewport", "desktop")
        reached.setdefault(viewport, {})[page.get("step", "?")] = bool(page.get("success", True))
    return reached


def verdict(row: dict) -> str:
    """Rough "is this store good for a live demo?" label."""
    if row["error"]:
        return "skip (scan failed)"
    desktop = row["reached"].get("desktop", {})
    steps_ok = sum(1 for step in STEPS if desktop.get(step))
    if steps_ok == 3 and row["sdk"] not in ("none", "unknown", ""):
        return "GOOD for demo"
    if steps_ok >= 2:
        return "partial (some pages not reached)"
    return "weak (blocked or unusual layout)"


def scan_one(url: str, out_dir: Path, include_mobile: bool) -> dict:
    """Run scanner -> AI -> ranker on one store; never raises."""
    from ai_engine import analyze_checkout_detailed
    from impact_ranker import health_score, rank_issues
    from scanner import BrowserConfig, scan_store

    row = {"url": url, "error": "", "reached": {}, "sdk": "", "issues": [], "health": None,
           "seconds": 0.0, "warnings": []}
    started = time.monotonic()
    try:
        config = BrowserConfig(screenshots_dir=str(out_dir / slug(url)))
        scan = scan_store(url, include_mobile=include_mobile, config=config)
        row["reached"] = pages_reached(scan)
        row["sdk"] = scan.get("detected_sdk_version") or scan.get("paypal_sdk_version") or "none"
        if scan.get("status") == "failed" or not any(any(v.values()) for v in row["reached"].values()):
            row["error"] = "; ".join(map(str, scan.get("errors") or scan.get("warnings") or ["scan failed"]))[:300]
            row["seconds"] = round(time.monotonic() - started, 1)
            row["verdict"] = verdict(row)
            return row  # no pages reached: do not score an empty scan
        analysis = analyze_checkout_detailed(scan)
        ranked = rank_issues(analysis["issues"])
        row["issues"] = [f"{i['issue_id']} ({i['severity']})" for i in ranked]
        row["health"] = health_score(ranked)
        row["warnings"] = [str(w) for w in (scan.get("warnings") or []) + analysis["warnings"]][:5]
    except Exception as error:  # keep going with the next store
        row["error"] = f"{type(error).__name__}: {error}"[:300]
    row["seconds"] = round(time.monotonic() - started, 1)
    row["verdict"] = verdict(row)
    return row


def reached_text(row: dict) -> str:
    def mark(viewport):
        got = row["reached"].get(viewport, {})
        return "".join(STEP_LETTER[step] if got.get(step) else "-" for step in STEPS)
    return f"desktop {mark('desktop')} / mobile {mark('mobile')}"


def to_markdown(rows: list[dict]) -> str:
    lines = [
        "# Real-store trial",
        "",
        "Pages reached: P = product, C = cart, K = checkout, - = not reached.",
        "",
        "| Store | Verdict | Pages reached | PayPal SDK | Health | Issues | Time |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        issues = ", ".join(r["issues"]) or ("—" if not r["error"] else r["error"][:80])
        health = "—" if r["health"] is None else f"{r['health']}/100"
        lines.append(f"| {r['url']} | {r['verdict']} | {reached_text(r)} | {r['sdk'] or '—'} | {health} | {issues} | {r['seconds']}s |")
    lines += ["", "_Screenshots in this folder are of other companies' sites: do not commit them._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan public stores to pick good ones for the demo.")
    parser.add_argument("urls", nargs="*", help="store URLs (https://...)")
    parser.add_argument("--file", help="text file with one URL per line")
    parser.add_argument("--no-vision", action="store_true", help="rules only (faster, no Gemini calls)")
    parser.add_argument("--desktop-only", action="store_true", help="skip the mobile pass (faster)")
    args = parser.parse_args(argv)

    urls = read_urls(args)
    if not urls:
        parser.error("give at least one URL, or --file stores.txt")
    if args.no_vision:
        os.environ["AI_VISION_ENABLED"] = "false"

    run_dir = OUT_ROOT / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for number, url in enumerate(urls, 1):
        print(f"[{number}/{len(urls)}] {url} ...", flush=True)
        row = scan_one(url, run_dir, include_mobile=not args.desktop_only)
        rows.append(row)
        health = "—" if row["health"] is None else f"{row['health']}/100"
        print(f"    {row['verdict']} | {reached_text(row)} | SDK {row['sdk'] or '—'} | health {health} "
              f"| {len(row['issues'])} issue(s) | {row['seconds']}s", flush=True)
        if row["error"]:
            print(f"    error: {row['error']}", flush=True)
        if number < len(urls):
            time.sleep(PAUSE_BETWEEN_STORES_SECONDS)

    (run_dir / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (run_dir / "results.md").write_text(to_markdown(rows), encoding="utf-8")
    print(f"\nSaved: {run_dir / 'results.md'}")
    good = [r["url"] for r in rows if r["verdict"] == "GOOD for demo"]
    print("Good for the demo:", ", ".join(good) if good else "none yet. Try more stores.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
