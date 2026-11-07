"""
Try the vision AI on your own screenshots (no scanner needed).

Usage (from the project root, with the venv active):

    python -m ai_engine.try_vision path\\to\\cart.png
    python -m ai_engine.try_vision cart.png checkout.png --labels "cart (desktop)" "checkout (mobile)"
    python -m ai_engine.try_vision --list-models

Labels tell the model what each image is: "<step> (<viewport>)", where step is
cart or checkout and viewport is desktop or mobile. Without labels, every image
is treated as "checkout (desktop)".

The AI provider and key come from .env (AI_PROVIDER + its API key).
Images should be PNG files.
"""

import argparse
import json
import sys
from pathlib import Path

from ai_engine.errors import ModuleError
from ai_engine.vision import list_gemini_models, run_vision_checks

VALID_STEPS = ("cart", "checkout")
VALID_VIEWPORTS = ("desktop", "mobile")


def parse_label(label: str) -> tuple[str, str]:
    """Turn 'cart (mobile)' into ('cart', 'mobile'); fall back to checkout/desktop."""
    text = label.lower()
    step = next((s for s in VALID_STEPS if s in text), "checkout")
    viewport = next((v for v in VALID_VIEWPORTS if v in text), "desktop")
    return step, viewport


def build_scan_data(images: list[str], labels: list[str] | None = None) -> dict:
    """Build a minimal ScanData dict around the given screenshot files."""
    labels = labels or []
    pages = []
    for index, image in enumerate(images):
        step, viewport = parse_label(labels[index] if index < len(labels) else "")
        pages.append(
            {
                "step": step,
                "viewport": viewport,
                "url": "",
                "screenshot_path": str(Path(image).resolve()),
                "scripts": [],
                "paypal_elements": [],
                "viewport_height": 844 if viewport == "mobile" else 900,
            }
        )
    return {"scan_id": "try_vision", "store_url": "", "pages": pages, "paypal_sdk_version": "none", "warnings": []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the CheckoutPilot vision check on screenshots.")
    parser.add_argument("images", nargs="*", help="PNG screenshot files")
    parser.add_argument("--labels", nargs="*", help='One label per image, e.g. "cart (desktop)"')
    parser.add_argument("--list-models", action="store_true", help="List Gemini models your key can use")
    args = parser.parse_args(argv)

    if args.list_models:
        try:
            models = list_gemini_models()
        except ModuleError as error:
            print(f"Failed with {error.code}: {error.message}")
            return 2
        print("Gemini models your key can use (set one as AI_MODEL or AI_FALLBACK_MODEL in .env):")
        for name in models:
            print(f"  {name}")
        return 0

    if not args.images:
        parser.error("give at least one screenshot file, or use --list-models")

    missing = [image for image in args.images if not Path(image).is_file()]
    if missing:
        print(f"File not found: {', '.join(missing)}")
        return 1

    scan_data = build_scan_data(args.images, args.labels)
    print("Sending screenshots to the vision model...")
    for page in scan_data["pages"]:
        print(f"  - {page['step']} ({page['viewport']}): {page['screenshot_path']}")

    try:
        issues, warnings = run_vision_checks(scan_data)
    except ModuleError as error:
        print(f"\nFailed with {error.code}: {error.message}")
        return 2

    print(f"\nVision model found {len(issues)} issue(s):")
    print(json.dumps(issues, indent=2))
    for warning in warnings:
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
