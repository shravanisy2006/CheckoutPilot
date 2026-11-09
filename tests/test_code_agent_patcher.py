"""
Tests for the non-destructive code patcher and validators.
"""

import shutil
from pathlib import Path

from code_agent.patcher import (
    PatchEngine,
    apply_upgrade,
    validate_balanced_brackets,
    validate_business_preservation,
    validate_html_syntax_and_ids,
    validate_python_syntax,
)
from code_agent.upgrade_agent import generate_upgrade


def test_validate_python_syntax():
    """Verify Python AST syntax validator catches broken code."""
    valid_code = "def add(a, b):\n    return a + b\n"
    ok, err = validate_python_syntax(valid_code)
    assert ok is True
    assert err is None

    broken_code = "def broken(:\n    pass\n"
    ok, err = validate_python_syntax(broken_code)
    assert ok is False
    assert "SyntaxError" in err


def test_validate_html_ids():
    """Verify HTML validator enforces retention of required stable IDs."""
    html = '<form id="shipping-form"><input id="email"></form>'
    ok, err = validate_html_syntax_and_ids(html, required_ids=["shipping-form"])
    assert ok is True

    ok, err = validate_html_syntax_and_ids(html, required_ids=["missing-id"])
    assert ok is False
    assert "Missing required stable DOM IDs" in err


def test_validate_business_preservation():
    """Verify preservation check alerts if business variables are stripped."""
    orig = "PRODUCTS = {'pen': 35}\ncalculate_total()\n"
    safe = "PRODUCTS = {'pen': 35}\ncalculate_total()\n# added endpoint"
    ok, err = validate_business_preservation(orig, safe, ["PRODUCTS", "calculate_total"])
    assert ok is True

    stripped = "calculate_total()\n# deleted products"
    ok, err = validate_business_preservation(orig, stripped, ["PRODUCTS"])
    assert ok is False
    assert "business code was removed" in err


def test_end_to_end_store_patching(tmp_path):
    """
    Test applying full upgrade patches to an isolated copy of legacy_store.
    Verifies that the patched store incorporates all v6 features while
    preserving all existing catalogue, pricing, and checkout forms.
    """
    source_store = Path("demo_stores/legacy_store").resolve()
    target_store = tmp_path / "test_store"
    shutil.copytree(source_store, target_store)

    # Execute the upgrade
    result = generate_upgrade(str(target_store))

    assert result["success"] is True
    assert len(result["files_changed"]) >= 4
    assert "app.py" in result["files_changed"]
    assert "templates/checkout.html" in result["files_changed"]
    assert "templates/cart.html" in result["files_changed"]
    assert "static/style.css" in result["files_changed"]
    assert "static/paypal.js" in result["files_changed"]

    # 1. Verify app.py has client-token endpoint and valid Python syntax
    patched_app = (target_store / "app.py").read_text(encoding="utf-8")
    valid_ast, ast_err = validate_python_syntax(patched_app)
    assert valid_ast is True, f"Patched app.py has syntax error: {ast_err}"
    assert "/api/paypal/client-token" in patched_app
    assert "PRODUCTS" in patched_app
    assert "calculate_total" in patched_app
    assert '"paypal_sdk": "v6"' in patched_app

    # 2. Verify templates/checkout.html upgraded to v6 and mobile layout class
    patched_checkout = (target_store / "templates" / "checkout.html").read_text(encoding="utf-8")
    assert "{{PAYPAL_SDK_URL}}" in patched_checkout
    assert "paypal.com/sdk/js" not in patched_checkout
    assert "checkout upgraded" in patched_checkout
    assert "<paypal-button" in patched_checkout
    assert 'id="shipping-form"' in patched_checkout  # Stable ID preserved

    # 3. Verify templates/cart.html has express checkout button
    patched_cart = (target_store / "templates" / "cart.html").read_text(encoding="utf-8")
    assert "<paypal-button" in patched_cart
    assert 'id="paypal-button-container"' in patched_cart
    assert 'id="go-to-checkout"' in patched_cart  # Stable ID preserved

    # 4. Verify static/style.css has mobile reordering
    patched_css = (target_store / "static" / "style.css").read_text(encoding="utf-8")
    assert ".checkout.upgraded" in patched_css
    assert 'grid-template-areas: "summary" "form"' in patched_css

    # 5. Verify static/paypal.js exists and initializes v6
    assert (target_store / "static" / "paypal.js").exists()
    paypal_js = (target_store / "static" / "paypal.js").read_text(encoding="utf-8")
    assert "createPayPalOneTimePaymentSession" in paypal_js
    assert "/api/paypal/client-token" in paypal_js


def test_upgrade_arbitrary_repo_structure(tmp_path):
    """
    Test that the patcher successfully discovers and upgrades an arbitrary repo
    with custom directory structure (src/server.py, views/checkout.html, assets/css/main.css).
    """
    custom_repo = tmp_path / "custom_store"
    src_dir = custom_repo / "src"
    views_dir = custom_repo / "views"
    assets_dir = custom_repo / "assets"
    src_dir.mkdir(parents=True)
    views_dir.mkdir(parents=True)
    assets_dir.mkdir(parents=True)

    # 1. Custom server file: src/server.py
    server_py = (
        'from fastapi import FastAPI, HTTPException\n'
        'app = FastAPI()\n'
        'PRODUCTS = {"pen": 35.0}\n'
        'def calculate_total(items): return "35.00"\n'
        'def list_products(): return PRODUCTS\n'
        'MAX_QTY_PER_ITEM = 5\n'
        'def _paypal_client(): return None\n'
        '@app.post("/api/orders")\n'
        'def create_order(): return {"id": "123"}\n'
    )
    (src_dir / "server.py").write_text(server_py, encoding="utf-8")

    # 2. Custom checkout template: views/checkout.html
    checkout_html = (
        '<html><head>\n'
        '<script src="https://www.paypal.com/sdk/js?client-id=sb"></script>\n'
        '</head><body>\n'
        '<div class="checkout">\n'
        '<form id="shipping-form"><input id="email"></form>\n'
        '<aside id="order-summary">\n'
        '<div id="cart-lines"></div><div id="cart-total">$35.00</div>\n'
        '<div id="paypal-button-container"></div>\n'
        '</aside></div></body></html>'
    )
    (views_dir / "checkout.html").write_text(checkout_html, encoding="utf-8")

    # 3. Custom cart template: views/cart.html
    cart_html = (
        '<html><head><title>Your cart</title></head><body>\n'
        '<div id="cart-lines"></div><div id="cart-total">$35.00</div>\n'
        '<div id="cart-empty" hidden></div>\n'
        '<div class="actions"><a id="go-to-checkout">Checkout</a><button id="clear-cart">Clear</button></div>\n'
        '</body></html>'
    )
    (views_dir / "cart.html").write_text(cart_html, encoding="utf-8")

    # 4. Custom stylesheet: assets/site.css
    site_css = '.checkout { display: grid; }\n@media (max-width: 760px) { .checkout { grid-template-columns: 1fr; } }\n'
    (assets_dir / "site.css").write_text(site_css, encoding="utf-8")

    # Execute the upgrade
    result = generate_upgrade(str(custom_repo))

    assert result["success"] is True
    assert "src/server.py" in result["files_changed"]
    assert "views/checkout.html" in result["files_changed"]
    assert "views/cart.html" in result["files_changed"]
    assert "assets/site.css" in result["files_changed"]

    # Verify server.py received client-token endpoint
    updated_server = (src_dir / "server.py").read_text(encoding="utf-8")
    assert "/api/paypal/client-token" in updated_server
    valid_ast, _ = validate_python_syntax(updated_server)
    assert valid_ast is True

    # Verify views/checkout.html received v6 web component
    updated_checkout = (views_dir / "checkout.html").read_text(encoding="utf-8")
    assert "<paypal-button" in updated_checkout
    assert "checkout upgraded" in updated_checkout

    # Verify views/cart.html received express button
    updated_cart = (views_dir / "cart.html").read_text(encoding="utf-8")
    assert "<paypal-button" in updated_cart



def test_validate_balanced_brackets_javascript():
    """Verify JS/TS bracket validator detects unbalanced code."""
    valid_js = "function pay() { const cart = [1, 2]; if (cart.length > 0) { return true; } }"
    ok, err = validate_balanced_brackets(valid_js)
    assert ok is True
    assert err is None

    broken_js = "function pay() { const cart = [1, 2; }"
    ok, err = validate_balanced_brackets(broken_js)
    assert ok is False
    assert "Mismatched" in err or "bracket" in err.lower()


def test_synthesize_file_patch_with_mock_llm():
    """Verify LLM patch synthesizer cleanly updates a file while respecting business preservation."""
    from code_agent.patcher import synthesize_file_patch
    from tests.test_agentic_coding_agent import MockLLMAdapter

    orig_server = (
        'const express = require("express");\n'
        'const app = express();\n'
        'const PRODUCTS = [{ id: "pen", price: 35.0 }];\n'
        'app.post("/api/orders", (req, res) => res.json({ id: "123" }));\n'
        'app.listen(3000);\n'
    )

    valid_llm_response = (
        '```javascript\n'
        'const express = require("express");\n'
        'const app = express();\n'
        'const PRODUCTS = [{ id: "pen", price: 35.0 }];\n'
        'app.get("/api/paypal/client-token", (req, res) => res.json({ accessToken: "mock-token" }));\n'
        'app.post("/api/orders", (req, res) => res.json({ id: "123" }));\n'
        'app.listen(3000);\n'
        '```'
    )

    mock_llm = MockLLMAdapter()
    mock_llm.generate_text = lambda prompt, system_prompt=None: valid_llm_response

    result = synthesize_file_patch("server.js", orig_server, "Add client token endpoint", llm=mock_llm)
    assert result is not None
    assert "/api/paypal/client-token" in result
    assert "PRODUCTS" in result

    # Test safety rejection: if LLM output strips PRODUCTS
    bad_llm_response = '```javascript\napp.get("/api/paypal/client-token", ...);\n```'
    mock_llm.generate_text = lambda prompt, system_prompt=None: bad_llm_response
    rejected = synthesize_file_patch("server.js", orig_server, "Add client token endpoint", llm=mock_llm)
    assert rejected is None  # Must be rejected to protect business logic
