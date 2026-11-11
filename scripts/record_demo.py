"""
Re-record Demo Mode from one REAL live run, so Demo replays exactly what Live produces.

Start the demo in real mode first (PayPal Sandbox + Gemini keys in .env), then in a second terminal:

    python run_demo.py                      # terminal 1, leave it running
    python -m scripts.record_demo           # terminal 2 (takes ~3 minutes)

What it does, through the same API the dashboard uses:
  1. scans the example store      (http://localhost:8101)
  2. writes the fix               (POST /api/fix, code agent + browser self-test)
  3. proves it                    (POST /api/verify: two real PayPal Sandbox payments)
  4. re-measures                  (POST /api/fix/<id>/rescan: the same scanner on the fixed copy)

Then it saves the run as the dashboard's Demo recording:
  frontend-react/src/lib/checkout/sample_result.json   (and docs/sample_result.json)
  frontend-react/public/demo/*.png                      (the screenshots of this run)

Safety: it refuses to save a simulated (mock) run or a failed verification, and it never
saves the buyer's email, passwords or keys (it checks the result for them before writing).
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "http://localhost:8000"
LEGACY, UPGRADED = "http://localhost:8101", "http://localhost:8102"
FIXABLE = ["sdk_outdated", "no_paypal_on_cart", "button_below_fold_mobile"]

DEMO_IMG_DIR = ROOT / "frontend-react" / "public" / "demo"
SAMPLE_PATHS = [ROOT / "frontend-react" / "src" / "lib" / "checkout" / "sample_result.json",
                ROOT / "docs" / "sample_result.json"]
# The fixed names demo.ts shows as the main screenshots.
NAMED = {
    ("scan", "checkout", "desktop"): "legacy_checkout_desktop.png",
    ("scan", "checkout", "mobile"): "legacy_checkout_mobile.png",
    ("verify", "before"): "proof_before_v5.png",
    ("verify", "after"): "proof_after_v6.png",
}


def say(text: str) -> None:
    print(text, flush=True)


def call(method: str, path: str, body: dict | None = None, timeout: int = 600) -> dict:
    response = requests.request(method, API + path, json=body, timeout=timeout)
    try:
        data = response.json()
    except ValueError:
        data = {"detail": response.text[:300]}
    if response.status_code >= 400:
        raise SystemExit(f"{method} {path} failed ({response.status_code}): {data.get('detail', data)}")
    return data


def local_file(url: str) -> Path | None:
    """'/files/scans/x/y.png' -> <project>/outputs/scans/x/y.png (the backend serves outputs/ at /files)."""
    if not isinstance(url, str) or not url.startswith("/files/"):
        return None
    path = ROOT / "outputs" / url[len("/files/"):]
    return path if path.is_file() else None


def copy_images(run: dict, out_dir: Path) -> dict:
    """Copy every screenshot the run refers to into public/demo/ and point the JSON at /demo/..."""
    out_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}

    def visit(node):
        if isinstance(node, dict):
            return {k: visit(v) for k, v in node.items()}
        if isinstance(node, list):
            return [visit(v) for v in node]
        source = local_file(node)
        if source is None:
            return "" if isinstance(node, str) and node.startswith("/files/") else node
        if node not in copied:
            name = "rec_" + re.sub(r"[^a-zA-Z0-9_.-]+", "_", "_".join(Path(node).parts[-2:]))
            shutil.copyfile(source, out_dir / name)
            copied[node] = f"/demo/{name}"
        return copied[node]

    return visit(run), len(copied)


def copy_named(run_raw: dict, out_dir: Path) -> list[str]:
    """The main screenshots demo.ts shows: checkout (desktop/mobile) and the two success pages."""
    done = []
    for page in run_raw["scan"].get("pages", []):
        key = ("scan", page.get("step"), page.get("viewport"))
        if key in NAMED and (src := local_file(page.get("screenshot_url", ""))):
            shutil.copyfile(src, out_dir / NAMED[key])
            done.append(NAMED[key])
    for side in ("before", "after"):
        shots = (run_raw["verify"].get(side) or {}).get("screenshots") or []
        files = [local_file(s) for s in shots]
        files = [f for f in files if f]
        if files:
            shutil.copyfile(files[-1], out_dir / NAMED[("verify", side)])  # last = the success page
            done.append(NAMED[("verify", side)])
    return done


def private_values() -> list[str]:
    """Things that must never be saved: buyer login, keys (read from .env / the environment)."""
    from dotenv import dotenv_values
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    names = ["PAYPAL_SANDBOX_BUYER_EMAIL", "PAYPAL_SANDBOX_BUYER_PASSWORD", "PAYPAL_CLIENT_SECRET",
             "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "NVIDIA_API_KEY"]
    return [v for n in names if (v := (env.get(n) or "").strip()) and len(v) >= 6 and not v.startswith("your-")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-record Demo Mode from one real live run.")
    parser.add_argument("--dry-run", action="store_true", help="run everything but don't overwrite the recording")
    args = parser.parse_args(argv)

    try:
        health = requests.get(API + "/api/health", timeout=5).json()
    except requests.RequestException:
        raise SystemExit("The backend is not running. Start `python run_demo.py` (real mode) first.")
    say(f"Backend OK ({health.get('status', '?')}). Recording a live run of {LEGACY} ...")

    started = time.monotonic()
    say("1/4 Scanning the example store ...")
    scan = call("POST", "/api/scan", {"store_url": LEGACY})
    say(f"    health {scan['health_score']}/100, {len(scan['issues'])} issues")
    found = {i["issue_id"] for i in scan["issues"]}
    issue_ids = [i for i in FIXABLE if i in found]

    say("2/4 Writing the fix (code agent + browser self-test) ...")
    fix = call("POST", "/api/fix", {"scan_id": scan["scan_id"], "issue_ids": issue_ids})
    say(f"    {len(fix['files'])} files changed, plan: {fix.get('generated_by')}, browser check: {fix.get('browser_check')}")

    say("3/4 Proving it with two PayPal Sandbox payments (1-2 minutes, don't touch the browser) ...")
    verify = call("POST", "/api/verify", {"fix_id": fix["fix_id"]}, timeout=900)
    if verify.get("simulated"):
        raise SystemExit("This was a SIMULATED run (mock mode). Start `python run_demo.py` without --mock and retry.")
    if not verify.get("safe_to_approve"):
        raise SystemExit(f"The verification did not pass, so it was not recorded: {verify.get('summary')}")
    say(f"    passed: before {verify['before'].get('order_id')}, after {verify['after'].get('order_id')}")

    say("4/4 Re-measuring: scanning the code agent's fixed copy ...")
    rescan = call("POST", f"/api/fix/{fix['fix_id']}/rescan", {})
    say(f"    health {scan['health_score']} -> {rescan['health_score']}/100")

    when = datetime.now(timezone.utc).strftime("%d %b %Y")
    raw = {
        "_about": (
            "Real CheckoutPilot output for the demo store Inkwell & Co., recorded by scripts/record_demo.py "
            f"on {when} from one live run: scan (scanner + AI + impact ranker), fix (code agent, "
            f"plan: {fix.get('generated_by')}, browser self-test: {fix.get('browser_check')}), and two real "
            "PayPal Sandbox payments made by sandbox_verifier. Demo Mode replays exactly this."
        ),
        "scan": scan, "fix": fix, "verify": verify, "rescan_after_fix": rescan,
    }

    text = json.dumps(raw)
    leaked = [v for v in private_values() if v in text]
    if leaked:
        raise SystemExit("Stopped: the result contains a private value from .env (buyer login or a key). Nothing saved.")

    if args.dry_run:
        say(f"\nDry run OK in {time.monotonic() - started:.0f}s. Nothing was saved.")
        return 0

    recorded, images = copy_images(raw, DEMO_IMG_DIR)
    named = copy_named(raw, DEMO_IMG_DIR)
    for path in SAMPLE_PATHS:
        path.write_text(json.dumps(recorded, indent=2) + "\n", encoding="utf-8")
    say(f"\nSaved the new Demo recording ({images} screenshots + {', '.join(named)}).")
    say("Restart the dashboard (Ctrl+C, then python run_demo.py) and check Demo mode.")
    say("Then commit: frontend-react/src/lib/checkout/sample_result.json docs/sample_result.json frontend-react/public/demo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
