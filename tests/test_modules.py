"""
Smoke tests: every module imports and its placeholder functions return the
expected shape. Update these as you implement real logic in each module.
"""

from ai_engine import analyze_checkout
from code_agent import create_upgrade_plan, generate_upgrade
from impact_ranker import rank_gaps
from paypal_integration import PayPalClient
from sandbox_verifier import verify_checkout_mock
from scanner import scan_store


def test_scanner_returns_dict():
    result = scan_store("https://example.com")
    assert result["store_url"] == "https://example.com"
    assert isinstance(result["pages"], list)


def test_ai_engine_returns_list():
    assert isinstance(analyze_checkout({"store_url": "x", "pages": []}), list)


def test_ranker_adds_impact_field():
    ranked = rank_gaps([{"gap_id": "sdk_v5", "title": "Old SDK"}])
    assert "estimated_impact" in ranked[0]


def test_code_agent_placeholders():
    assert create_upgrade_plan(".", []) == []
    assert "pull_request_url" in generate_upgrade(".", [])


def test_paypal_client_creates():
    client = PayPalClient()
    assert client.api_base.startswith("https://")


def test_verifier_returns_result():
    # The real verifier needs a browser and PayPal; see tests/test_sandbox_verifier.py.
    result = verify_checkout_mock("http://localhost:8101", label="before")
    for key in ("store_url", "label", "purchase_succeeded", "order_id", "payment_saved", "screenshots"):
        assert key in result
