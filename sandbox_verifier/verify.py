"""
Run a real PayPal Sandbox test purchase from the command line.

From the project root (venv active):
    python -m sandbox_verifier.verify legacy --headed      # watch it pay on the old store
    python -m sandbox_verifier.verify upgraded --headed
    python -m sandbox_verifier.verify both                 # before vs after comparison
    python -m sandbox_verifier.verify upgraded --page cart # pay from the cart page
    python -m sandbox_verifier.verify http://localhost:8103 # any local store already running

Stores you name ("legacy", "upgraded") are started for you and stopped afterwards.
Screenshots go to outputs/verifications/<id>/. Exit code 0 = payment proven.
"""

import argparse
import json
import sys

import requests

from demo_stores.serve import resolve_store, start_store, stop_store
from sandbox_verifier.errors import ModuleError
from sandbox_verifier.verifier import compare_runs, verify_checkout


def _already_running(url: str) -> bool:
    try:
        return requests.get(f"{url}/health", timeout=2).status_code == 200
    except requests.RequestException:
        return False


def run_one(target: str, label: str, args) -> dict:
    """Start the store if needed, verify it, stop it again."""
    started_port = None
    if target.startswith("http"):
        url = target.rstrip("/")
    else:
        store_dir, port = resolve_store(target)
        if port is None:
            raise ModuleError("VERIFY_BAD_STORE_URL", f"Unknown store {target!r}. Use legacy, upgraded or a URL.")
        url = f"http://localhost:{port}"
        if not _already_running(url):
            print(f"Starting {target} store on {url} ...")
            start_store(store_dir, port)
            started_port = port
    try:
        print(f"Verifying {url} ({label}) - this takes about 30-60 seconds ...")
        return verify_checkout(url, label=label, page=args.page,
                               headless=not args.headed, slow_mo=300 if args.headed else 0)
    finally:
        if started_port:
            stop_store(started_port)


def print_result(result: dict) -> None:
    mark = "PASSED" if result["purchase_succeeded"] else "FAILED"
    print(f"\n[{mark}] {result['label']}: {result['store_url']}")
    for step in result["steps"]:
        print(f"   {'ok ' if step['ok'] else 'X  '} {step['at_seconds']:>5}s  {step['name']}"
              + (f"  ({step['detail']})" if step["detail"] else ""))
    if result["purchase_succeeded"]:
        print(f"   Order {result['order_id']}  status {result['order_status'] or '?'}  "
              f"{result['amount']} {result['currency']}  SDK {result['paypal_sdk']}")
    else:
        print(f"   Error {result['error_code']}: {result['error_message']}")
    for warning in result["warnings"]:
        print(f"   Warning: {warning}")
    if result["screenshots"]:
        print(f"   Screenshots: {result['screenshots'][0].rsplit('/', 1)[0]}/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove a checkout works with a PayPal Sandbox purchase.")
    parser.add_argument("target", help="legacy, upgraded, both, or a local store URL")
    parser.add_argument("--headed", action="store_true", help="show the browser window (slower, good for demos)")
    parser.add_argument("--page", choices=["checkout", "cart"], default="checkout",
                        help="where to click PayPal (cart works on the upgraded store only)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    try:
        if args.target == "both":
            before = run_one("legacy", "before", args)
            print_result(before)
            after = run_one("upgraded", "after", args)
            print_result(after)
            comparison = compare_runs(before, after)
            print(f"\n{comparison['summary']}")
            for change in comparison["changes"]:
                print(f" - {change}")
            if args.json:
                print(json.dumps(comparison, indent=2))
            return 0 if comparison["safe_to_approve"] else 1
        result = run_one(args.target, "after" if args.target == "upgraded" else "before", args)
    except ModuleError as error:
        print(f"ERROR {error.code}: {error.message}")
        return 2
    print_result(result)
    if args.json:
        print(json.dumps(result, indent=2))
    return 0 if result["purchase_succeeded"] else 1


if __name__ == "__main__":
    sys.exit(main())
