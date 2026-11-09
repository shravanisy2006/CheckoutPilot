"""
Test-drive a patched store in a real browser BEFORE the fix is proposed.

The store copy is started on a free local port and opened in headless Chromium. Nothing leaves
the laptop: every request to another host is blocked, the PayPal v6 SDK is replaced by a small
fake (FAKE_V6_SDK) that behaves like the real one where it matters, and the store's three PayPal
calls get fake answers. Then we buy: add to cart -> checkout (and cart) -> click the PayPal
button -> the success page must load.

This catches what text checks cannot: a script that fails to load, a v5 component name, a page
that no longer draws the cart, two scripts fighting over the same function. The real proof is
still the Sandbox payment in POST /api/verify; this check just stops broken fixes earlier.
"""

import json
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

# Like the real SDK: defines <paypal-button>, rejects v5 component names, needs a token or
# client ID, and start() needs a promise of {orderId}.
FAKE_V6_SDK = """
if (!customElements.get("paypal-button")) {
  customElements.define("paypal-button", class extends HTMLElement {
    connectedCallback() { this.textContent = "PayPal"; this.style.minHeight = "40px"; }
  });
}
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

LOCAL_HOSTS = {"localhost", "127.0.0.1"}
TIMEOUT_MS = 10000


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _json(route, body: dict) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def _handle(route) -> None:
    """Fake PayPal; block every other host; let the local store answer the rest."""
    url = route.request.url
    host = urlparse(url).hostname or ""
    path = urlparse(url).path
    if "/web-sdk/v6/core" in path:
        route.fulfill(status=200, content_type="application/javascript", body=FAKE_V6_SDK)
    elif host not in LOCAL_HOSTS:
        route.abort()
    elif path == "/api/paypal/client-token":
        _json(route, {"accessToken": "SELF-TEST-TOKEN"})
    elif path == "/api/orders":
        _json(route, {"id": "SELFTEST1", "status": "CREATED"})
    elif path.startswith("/api/orders/") and path.endswith("/capture"):
        _json(route, {"id": "SELFTEST1", "status": "COMPLETED"})
    else:
        route.continue_()


def _buy(browser, url: str, step: str, **context) -> str:
    """Return "" if the purchase on this page works, else what went wrong."""
    ctx = browser.new_context(**context)
    page = ctx.new_page()
    page.route("**/*", _handle)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(url + "/")
        page.click("#add-to-cart", timeout=TIMEOUT_MS)
        page.goto(f"{url}/{step}")
        button = page.locator("#paypal-button-container paypal-button")
        try:
            button.wait_for(state="visible", timeout=TIMEOUT_MS)
        except Exception:
            status = page.locator("#order-status").first.inner_text() if page.locator("#order-status").count() else ""
            return f"{step}: the PayPal button never appeared ({status or 'no message'})"
        total = page.locator("#cart-total").inner_text() if page.locator("#cart-total").count() else ""
        if total.strip() in ("", "$0.00"):
            return f"{step}: the order total is {total or 'missing'} after adding a product"
        button.click()
        try:
            page.wait_for_url("**/success**", timeout=TIMEOUT_MS)
        except Exception:
            status = page.locator("#order-status").first.inner_text() if page.locator("#order-status").count() else ""
            return f"{step}: clicking PayPal did not finish the order ({status or 'no message'})"
        if errors:
            return f"{step}: JavaScript error: {errors[0]}"
        return ""
    except Exception as error:  # navigation problems, missing elements
        return f"{step}: {type(error).__name__}: {str(error).splitlines()[0][:200]}"
    finally:
        ctx.close()


def browser_check(store_dir: str | Path, pages: tuple[str, ...] = ("checkout", "cart")) -> list[str]:
    """Problems found by test-driving the store in a browser (empty list = it works).

    A page is only tested if its template has a <paypal-button> (e.g. a store without the
    cart fix is not asked to pay from the cart). Returns [] when the check is turned off
    with CODE_AGENT_BROWSER_CHECK=false, or when Playwright is not installed.
    """
    if os.getenv("CODE_AGENT_BROWSER_CHECK", "true").strip().lower() in ("0", "false", "no"):
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []
    from demo_stores.serve import start_store, stop_store

    store_dir = Path(store_dir)
    to_test = [p for p in pages
               if "<paypal-button" in _read(store_dir / "templates" / f"{p}.html")]
    if not to_test:
        return ["No page has a v6 <paypal-button> to test."]

    # Own thread: Playwright's sync API refuses to run where another Playwright or an asyncio
    # loop is already running (e.g. inside tests or an async server).
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_drive, store_dir, to_test, sync_playwright, start_store, stop_store).result(timeout=180)


def _drive(store_dir: Path, to_test: list[str], sync_playwright, start_store, stop_store) -> list[str]:
    port = _free_port()
    try:
        start_store(store_dir, port)
    except Exception as error:
        return [f"The patched store did not start: {error}"]
    problems = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                for step in to_test:
                    problem = _buy(browser, f"http://localhost:{port}", step)
                    if problem:
                        problems.append("Browser check, " + problem)
            finally:
                browser.close()
    finally:
        stop_store(port)
    return problems


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
