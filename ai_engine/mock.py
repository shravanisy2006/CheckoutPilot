"""
Mock AI engine: returns fixed fixture data with no AI call.

Used when MOCK_AI=true (backend) or when another member needs predictable
issues while building their own module.
"""

import copy
import json
from pathlib import Path
from ai_engine.rules import get_sdk_version

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def load_fixture(name: str) -> dict | list:
    """Load a JSON file from tests/fixtures/ by file name."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def analyze_checkout_mock(scan_data: dict | None = None) -> list[dict]:
    """
    Return the fixture issues for the legacy store.

    If scan_data says the store already uses SDK v6, return an empty list
    instead, so mock runs of the upgraded store look clean.
    """
    if scan_data and get_sdk_version(scan_data) == "v6":
        return []
    return copy.deepcopy(load_fixture("checkout_issues_legacy.json"))


def mock_scan_data(store: str = "legacy") -> dict:
    """Return the fixture ScanData for 'legacy' or 'upgraded'."""
    return copy.deepcopy(load_fixture(f"scan_data_{store}.json"))
