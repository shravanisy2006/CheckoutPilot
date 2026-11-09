"""
Tests for the code_agent analyzer module.
"""

import json
from pathlib import Path

from code_agent.analyzer import analyze_repository


def test_analyze_legacy_store_sdk():
    """Verify legacy store detects PayPal SDK v5 with expected query parameters."""
    ctx = analyze_repository("demo_stores/legacy_store")

    assert ctx.detected_sdk_version == "v5"
    assert len(ctx.sdk_references) >= 1

    sdk_ref = ctx.sdk_references[0]
    assert sdk_ref.version == "v5"
    assert "checkout.html" in sdk_ref.file_path
    assert sdk_ref.is_v6 is False
    assert sdk_ref.client_id_param == "{{PAYPAL_CLIENT_ID}}"
    assert sdk_ref.currency_param == "{{CURRENCY}}"
    assert sdk_ref.components_param == "buttons"


def test_analyze_legacy_store_buttons_and_missing_pages():
    """Verify detection of button containers and missing presentment on cart/product."""
    ctx = analyze_repository("demo_stores/legacy_store")

    # Checkout page must have the container
    checkout_containers = [c for c in ctx.button_containers if c.page_type == "checkout"]
    assert len(checkout_containers) >= 1
    assert checkout_containers[0].element_id == "paypal-button-container"
    assert checkout_containers[0].element_type == "container"

    # Cart and product templates exist but do not have PayPal buttons
    assert "cart" in ctx.missing_button_pages
    assert "product" in ctx.missing_button_pages


def test_analyze_legacy_store_scripts():
    """Verify JavaScript scan detects v5 paypal.Buttons and API endpoints."""
    ctx = analyze_repository("demo_stores/legacy_store")

    checkout_scripts = [cb for cb in ctx.client_callbacks if "checkout.js" in cb.file_path]
    assert len(checkout_scripts) == 1

    cb = checkout_scripts[0]
    assert cb.uses_paypal_buttons is True
    assert cb.uses_v6_instance is False
    assert cb.create_order_endpoint == "/api/orders"
    assert cb.capture_endpoint is not None
    assert "capture" in cb.capture_endpoint
    assert cb.client_token_endpoint is None


def test_analyze_legacy_store_server_routes():
    """Verify AST route scan detects order routes and flags missing client-token endpoint."""
    ctx = analyze_repository("demo_stores/legacy_store")

    assert ctx.has_create_order_route is True
    assert ctx.has_capture_order_route is True
    # In legacy store, client-token route is missing (needed for v6 upgrade)
    assert ctx.has_client_token_route is False

    paths = [ep.path for ep in ctx.server_endpoints]
    assert "/api/orders" in paths
    assert "/api/orders/{order_id}/capture" in paths


def test_analyze_legacy_store_mobile_layout():
    """Verify layout inspection flags button below form on mobile viewport."""
    ctx = analyze_repository("demo_stores/legacy_store")

    assert ctx.layout is not None
    assert ctx.layout.button_below_form_on_mobile is True
    assert ctx.layout.shipping_form_line < ctx.layout.summary_container_line


def test_analyze_upgraded_store():
    """Verify analyzer correctly analyzes the upgraded store (SDK v6, client-token, cart button)."""
    ctx = analyze_repository("demo_stores/upgraded_store")

    assert ctx.detected_sdk_version == "v6"
    assert ctx.has_client_token_route is True
    assert ctx.has_create_order_route is True
    assert ctx.has_capture_order_route is True

    # Cart page in upgraded store now has a paypal button
    cart_containers = [c for c in ctx.button_containers if c.page_type == "cart"]
    assert len(cart_containers) >= 1
    cart_elem_ids = [c.element_id for c in cart_containers]
    assert "paypal-button-container" in cart_elem_ids or "paypal-button" in cart_elem_ids
    assert "cart" not in ctx.missing_button_pages

    # Mobile reordering is active in upgraded store
    assert ctx.layout is not None
    assert ctx.layout.button_below_form_on_mobile is False


def test_guided_correlation_with_fixture_data():
    """Verify guided mode correctly incorporates gaps and scan metadata."""
    fixture_path = Path("tests/fixtures/checkout_issues_legacy.json")
    assert fixture_path.exists()
    issues = json.loads(fixture_path.read_text(encoding="utf-8"))

    ctx = analyze_repository("demo_stores/legacy_store", gaps=issues)

    assert len(ctx.guided_gaps) == len(issues)
    issue_ids = [g["issue_id"] for g in ctx.guided_gaps]
    assert "sdk_outdated" in issue_ids
    assert "no_paypal_on_cart" in issue_ids

    # Context dictionary conversion check
    ctx_dict = ctx.to_dict()
    assert isinstance(ctx_dict, dict)
    assert ctx_dict["detected_sdk_version"] == "v5"
    assert len(ctx_dict["guided_gaps"]) == len(issues)


def test_nonexistent_directory_handling():
    """Verify non-existent paths produce warnings instead of raising unhandled exceptions."""
    ctx = analyze_repository("non_existent_directory_xyz")
    assert len(ctx.warnings) >= 1
    assert "does not exist" in ctx.warnings[0]
