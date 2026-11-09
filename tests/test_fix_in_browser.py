"""
The code agent's patched store must really work in a browser, not just look right.

A fake PayPal v6 SDK stands in for www.sandbox.paypal.com (no internet needed). It behaves like
the real one where it matters: it rejects v5 component names ("unrecognized component in
createInstance: buttons"), needs a client token or client ID, and runs a one-time payment session
that expects a promise of {orderId}. The store's three PayPal calls (client token, create order,
capture) get fake answers in the browser, so the whole purchase runs end to end with no keys.
The store's server side is checked too: the patched app must answer /api/paypal/client-token.

Run: pytest tests/test_fix_in_browser.py -v
"""

import json
import socket
from pathlib import Path

import pytest
import requests

from code_agent.fix_builder import build_fix
from demo_stores.serve import start_store, stop_store

LEGACY = Path("demo_stores/legacy_store")
UPGRADED = Path("demo_stores/upgraded_store")

FAKE_V6_SDK = """
// Like the real SDK, define the <paypal-button> element so it has something to show.
customElements.define("paypal-button", class extends HTMLElement {
  connectedCallback() { this.textContent = "PayPal"; this.style.minHeight = "40px"; }
});
window.paypal = {
  createInstance: async function (options) {
    const known = ["paypal-payments", "venmo-payments", "paypal-messages"];
    (options.components || []).forEach(function (c) {
      if (known.indexOf(c) < 0) throw new Error("unrecognized component in createInstance: " + c);
    });
    if (!options.clientToken && !options.clientId) throw new Error("clientToken or clientId is required");
    return {
      findEligibleMethods: async function () { return { isEligible: function (m) { return m === "paypal"; } }; },
      createPayPalOneTimePaymentSession: function (callbacks) {
        return {
          start: async function (opts, orderPromise) {
            const order = await orderPromise;
            if (!order || !order.orderId) throw new Error("start() needs a promise of {orderId}");
            await callbacks.onApprove({ orderId: order.orderId });
          },
        };
      },
    };
  },
};
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def mock_paypal():
    """Kept for readability: PayPal is faked in the browser (see _page)."""


def _json(route, body):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def _serve(folder: Path):
    port = _free_port()
    start_store(folder, port)
    return f"http://localhost:{port}", port


def _page(browser, **context):
    ctx = browser.new_context(**context)
    page = ctx.new_page()
    page.route("**/web-sdk/v6/core*", lambda route: route.fulfill(
        status=200, content_type="application/javascript", body=FAKE_V6_SDK))
    page.route("**/api/paypal/client-token", lambda r: _json(r, {"accessToken": "FAKE-TOKEN"}))
    page.route("**/api/orders", lambda r: _json(r, {"id": "FAKEORDER1", "status": "CREATED"}))
    page.route("**/api/orders/*/capture", lambda r: _json(r, {"id": "FAKEORDER1", "status": "COMPLETED"}))
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


def _buy(browser, url: str, step: str, **context):
    """Add the pen to the cart, open the cart or checkout page and pay with the (fake) PayPal button."""
    ctx, page, errors = _page(browser, **context)
    try:
        page.goto(url + "/")
        page.click("#add-to-cart")
        page.goto(f"{url}/{step}")
        button = page.locator("#paypal-button-container paypal-button")
        button.wait_for(state="visible", timeout=10000)
        status = page.locator("#order-status").inner_text()
        total = page.locator("#cart-total").inner_text()
        box = button.bounding_box()
        button.click()
        page.wait_for_url("**/success**", timeout=10000)
        return {"status": status, "total": total, "box": box, "errors": errors}
    finally:
        ctx.close()


@pytest.mark.parametrize("step", ["checkout", "cart"])
def test_reference_store_pays_with_fake_v6_sdk(browser, mock_paypal, step):
    """Sanity check of the fake SDK: the Sandbox-verified reference store passes."""
    url, port = _serve(UPGRADED)
    try:
        result = _buy(browser, url, step)
    finally:
        stop_store(port)
    assert result["total"] != "$0.00" and result["errors"] == []


def test_agent_patched_store_pays_on_checkout_and_cart(browser, mock_paypal, tmp_path, monkeypatch):
    monkeypatch.setenv("CODE_AGENT_PROVIDER", "deterministic")
    fix = build_fix(LEGACY, ["sdk_outdated", "no_paypal_on_cart", "button_below_fold_mobile"],
                    fix_id="fix_browser", out_root=tmp_path)
    assert fix["status"] == "proposed", fix["errors"]
    url, port = _serve(tmp_path / "fix_browser")
    try:
        # Server side: the token route exists (no keys here, so PayPal itself answers with an error, not 404).
        assert requests.get(url + "/api/paypal/client-token", timeout=30).status_code in (200, 502, 503)
        checkout = _buy(browser, url, "checkout")
        cart = _buy(browser, url, "cart")
        mobile = _buy(browser, url, "checkout", viewport={"width": 390, "height": 844},
                      is_mobile=True, has_touch=True)
    finally:
        stop_store(port)

    for result in (checkout, cart, mobile):
        assert result["errors"] == [], result["errors"]
        assert "error" not in result["status"].lower()
        assert result["total"] != "$0.00"  # the order summary still shows the cart
    # Mobile: PayPal is on the first screen, without scrolling.
    assert mobile["box"]["y"] + mobile["box"]["height"] <= 844


def test_v5_component_name_is_caught_before_verify(tmp_path, monkeypatch):
    """The exact bug the Sandbox verification found: components: ["buttons"] in a v6 script."""
    monkeypatch.setenv("CODE_AGENT_PROVIDER", "deterministic")
    import code_agent.patcher.engine as engine
    bad = engine.get_paypal_v6_js().replace('components: ["paypal-payments"]', 'components: ["buttons"]')
    monkeypatch.setattr(engine, "get_paypal_v6_js", lambda: bad)
    fix = build_fix(LEGACY, ["sdk_outdated"], fix_id="fix_v5_name", out_root=tmp_path)
    assert fix["status"] == "failed"
    assert any('"buttons"' in p for p in fix["errors"])


def _fake_ai(plan: list[dict]):
    from code_agent.llm_client import BaseLLMAdapter

    class FakeAI(BaseLLMAdapter):
        def is_available(self):
            return True

        def generate_text(self, prompt, system_prompt=None):
            return json.dumps(plan)

    return FakeAI()


def test_ai_adding_the_token_route_does_not_skip_the_sdk_url(tmp_path, monkeypatch):
    """Seen live: the AI added /api/paypal/client-token itself, the template then skipped
    filling in {{PAYPAL_SDK_URL}}, and the checkout tried to load a script from "{{PAYPAL_SDK_URL}}"."""
    from code_agent.agentic import coding_agent
    route = ('@app.get("/api/paypal/client-token")\ndef client_token() -> dict:\n'
             '    return {"accessToken": _paypal_client().get_client_token()}\n\n\n@app.post("/api/orders")')
    plan = [{"gap_id": "sdk_outdated", "file": "app.py",
             "before_snippet": '@app.post("/api/orders")', "after_snippet": route}]
    monkeypatch.setattr(coding_agent, "get_llm_client", lambda: _fake_ai(plan))
    fix = build_fix(LEGACY, ["sdk_outdated", "no_paypal_on_cart"], fix_id="fix_ai_route", out_root=tmp_path)
    assert fix["status"] == "proposed", fix["errors"]
    assert fix["browser_check"] == "passed"
    app = (tmp_path / "fix_ai_route" / "app.py").read_text(encoding="utf-8")
    assert 'html.replace("{{PAYPAL_SDK_URL}}"' in app


def test_ai_edit_that_breaks_the_page_falls_back_to_template(tmp_path, monkeypatch):
    """Text checks can't see a broken script; the browser check can, and the template is used instead."""
    from code_agent.agentic import coding_agent
    # Valid on its own, but clashes with paypal.js's function showStatus (a SyntaxError in the browser).
    plan = [{"gap_id": "no_paypal_on_cart", "file": "templates/cart.html",
             "before_snippet": '<script src="/static/cart.js"></script>',
             "after_snippet": '<script>const showStatus = null;</script>\n  <script src="/static/cart.js"></script>'}]
    monkeypatch.setattr(coding_agent, "get_llm_client", lambda: _fake_ai(plan))
    fix = build_fix(LEGACY, ["sdk_outdated", "no_paypal_on_cart"], fix_id="fix_ai_broken", out_root=tmp_path)
    assert fix["generated_by"] == "template" and fix["status"] == "proposed"
    assert fix["browser_check"] == "passed"
    assert "Browser check" in fix["warnings"][0]
