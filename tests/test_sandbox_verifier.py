"""Tests for the sandbox verifier. Uses a fake local store + fake PayPal pages:
no real PayPal calls, no real payments. Run: pytest tests/test_sandbox_verifier.py -v"""

import socket
import textwrap

import pytest

from demo_stores.serve import start_store, stop_store
from sandbox_verifier import compare_runs, get_verifier, verify_checkout_mock
from sandbox_verifier import verifier
from sandbox_verifier.errors import ModuleError

# A fake store whose "PayPal button" opens fake PayPal login pages on the same server.
FAKE_STORE = textwrap.dedent('''
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    app = FastAPI()
    BUTTON = """<div id="paypal-button-container">
      <paypal-button style="display:block;width:300px;height:40px;background:#ffc439">PayPal</paypal-button></div>
      <p id="order-status"></p>
      <script>
        document.querySelector("paypal-button").addEventListener("click", () => {
          const w = window.open("http://127.0.0.1:" + location.port + "/fake-paypal/email", "pp", "width=500,height=600");
          const timer = setInterval(() => { if (w.closed) { clearInterval(timer);
            location.href = "/success?order=TESTORDER123"; } }, 200);
        });
      </script>"""
    PAGES = {
      "/": '<button id="add-to-cart">Add</button>',
      "/checkout": BUTTON,
      "/success": "<h1>Thanks</h1>",
      "/fake-paypal/email": '<input id="email"><button id="btnNext" onclick="location.href=\\'/fake-paypal/password?e=\\'+encodeURIComponent(email.value)">Next</button>',
      "/fake-paypal/password": '<input id="password" type="password"><button id="btnLogin" onclick="location.href=\\'/fake-paypal/review\\'">Log In</button>',
      "/fake-paypal/review": '<p>$35.00</p><button>Pay in 4</button><button onclick="window.close()">Complete Purchase</button>',
      "/fake-paypal/seller": '<p>You are logging in to the account of the seller for this purchase.</p>',
    }
    @app.get("/health")
    def health():
        return {"status": "ok"}
    @app.get("/{path:path}", response_class=HTMLResponse)
    def page(path: str):
        return "<html><body>" + PAGES.get("/" + path, "missing") + "</body></html>"
''')


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def buyer(monkeypatch):
    monkeypatch.setenv("PAYPAL_SANDBOX_BUYER_EMAIL", "sb-test@personal.example.com")
    monkeypatch.setenv("PAYPAL_SANDBOX_BUYER_PASSWORD", "test-password-123")


@pytest.fixture
def fake_store(tmp_path, monkeypatch):
    store = tmp_path / "fake_store"
    store.mkdir()
    (store / "app.py").write_text(FAKE_STORE)
    port = free_port()
    url = start_store(store, port)
    monkeypatch.setattr(verifier, "OUTPUT_ROOT", tmp_path / "verifications")
    monkeypatch.setattr(verifier, "SANDBOX_HOST", "127.0.0.1")  # treat our fake as "sandbox"
    yield url
    stop_store(port)


# ---------------------------------------------------------------- safety ---
@pytest.mark.parametrize("url", ["https://www.amazon.com", "http://example.com:8101", "ftp://localhost"])
def test_only_local_stores(url):
    with pytest.raises(ModuleError) as error:
        verifier.check_store_url(url)
    assert error.value.code == "VERIFY_BAD_STORE_URL"


@pytest.mark.parametrize("email, password", [
    ("", "x"), ("sb@personal.example.com", ""),
    ("buyer-sandbox-email@example.com", "x"),
    ("sb@personal.example.com", "your-sandbox-buyer-password-here"),
])
def test_buyer_credentials_required(monkeypatch, email, password):
    monkeypatch.setenv("PAYPAL_SANDBOX_BUYER_EMAIL", email)
    monkeypatch.setenv("PAYPAL_SANDBOX_BUYER_PASSWORD", password)
    with pytest.raises(ModuleError) as error:
        verifier.verify_checkout("http://localhost:8101")
    assert error.value.code == "VERIFY_NOT_CONFIGURED"


def test_sandbox_host_check():
    assert verifier.is_sandbox_url("https://www.sandbox.paypal.com/checkoutnow?token=1")
    assert not verifier.is_sandbox_url("https://www.paypal.com/checkoutnow?token=1")
    assert not verifier.is_sandbox_url("https://www.sandbox.paypal.com.evil.com/")


def test_order_id_from_url():
    assert verifier.order_id_from_url("http://localhost:8101/success?order=5S624309CY614830K") == "5S624309CY614830K"
    assert verifier.order_id_from_url("http://localhost:8101/success?order=<script>") == ""
    assert verifier.order_id_from_url("http://localhost:8101/success") == ""


# ------------------------------------------------- full run (fake PayPal) ---
def test_full_purchase_with_fake_paypal(fake_store, buyer, monkeypatch):
    monkeypatch.setattr(verifier, "_confirm_with_api",
                        lambda run, order_id: run.result.update(purchase_succeeded=True, order_status="COMPLETED",
                                                                api_confirmed=True))
    result = verifier.verify_checkout(fake_store, label="after")
    assert result["purchase_succeeded"], result
    assert result["order_id"] == "TESTORDER123"
    assert result["paypal_sdk"] == "v6"
    assert [s["name"] for s in result["steps"]] == [
        "added_to_cart", "paypal_button_found", "paypal_window_opened", "paid_in_paypal_window", "store_success_page"]
    assert len(result["screenshots"]) == 2
    assert "test-password-123" not in str(result)  # password never in the result


def test_refuses_to_type_login_outside_sandbox(fake_store, buyer, monkeypatch):
    monkeypatch.setattr(verifier, "SANDBOX_HOST", "www.sandbox.paypal.com")  # fake pages are NOT sandbox
    result = verifier.verify_checkout(fake_store)
    assert not result["purchase_succeeded"]
    assert result["error_code"] == "PAYPAL_NOT_SANDBOX"


def test_api_check_failure_falls_back_to_success_page(fake_store, buyer, monkeypatch):
    def broken_api(run, order_id):
        run.result["warnings"].append("Could not confirm with the Orders API: offline")
        run.result["purchase_succeeded"] = bool(order_id)
    monkeypatch.setattr(verifier, "_confirm_with_api", broken_api)
    result = verifier.verify_checkout(fake_store)
    assert result["purchase_succeeded"] and result["warnings"]


def test_reports_seller_account(tmp_path, buyer):
    from playwright.sync_api import sync_playwright
    page_html = "<html><body><p>You are logging in to the account of the seller for this purchase.</p></body></html>"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route("http://fake.test/**", lambda route: route.fulfill(body=page_html, content_type="text/html"))
        page.goto("http://fake.test/x")
        assert verifier.complete_paypal_popup(page, "a", "b", timeout=5, require_sandbox=False) == "BUYER_IS_SELLER"
        browser.close()


def test_missing_paypal_button(tmp_path, buyer, monkeypatch):
    store = tmp_path / "no_button_store"
    store.mkdir()
    (store / "app.py").write_text(FAKE_STORE.replace('"/checkout": BUTTON', '"/checkout": "<p id=order-status></p>"'))
    port = free_port()
    url = start_store(store, port)
    monkeypatch.setattr(verifier, "OUTPUT_ROOT", tmp_path / "out")
    monkeypatch.setattr(verifier, "BUTTON_WAIT_SECONDS", 2)
    try:
        result = verifier.verify_checkout(url)
    finally:
        stop_store(port)
    assert result["error_code"] == "PAYPAL_BUTTON_MISSING" and not result["purchase_succeeded"]


# ------------------------------------------------------- compare + mock ---
def test_compare_runs():
    before = verify_checkout_mock(label="before")
    after = verify_checkout_mock(label="after")
    comparison = compare_runs(before, after)
    assert comparison["safe_to_approve"] is True
    assert "PayPal SDK v5 -> v6" in comparison["changes"]

    broken = dict(after, purchase_succeeded=False, error_code="CAPTURE_FAILED")
    comparison = compare_runs(before, broken)
    assert comparison["safe_to_approve"] is False
    assert any("REGRESSION" in change for change in comparison["changes"])


def test_get_verifier_switch(monkeypatch):
    monkeypatch.setenv("MOCK_VERIFIER", "true")
    assert get_verifier() is verify_checkout_mock
    monkeypatch.setenv("MOCK_VERIFIER", "false")
    assert get_verifier() is verifier.verify_checkout


def test_window_closing_mid_check_counts_as_done():
    """Regression: PayPal closes its window right after Pay. That must not crash the verifier."""
    from playwright.sync_api import sync_playwright
    opener = "<html><body><script>window.open('http://fake.test/close', 'pp')</script></body></html>"
    closer = "<html><body><p>Processing...</p><script>setTimeout(() => window.close(), 400)</script></body></html>"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.route("http://fake.test/**", lambda route: route.fulfill(
            body=closer if route.request.url.endswith("/close") else opener, content_type="text/html"))
        page = context.new_page()
        with context.expect_page() as popup_info:
            page.goto("http://fake.test/start")
        popup = popup_info.value
        assert verifier.complete_paypal_popup(popup, "a", "b", timeout=10, require_sandbox=False) == ""
        browser.close()


def _run_popup_on(pages: dict, start: str, timeout: float = 15) -> tuple[str, list]:
    """Drive complete_paypal_popup over fake PayPal pages; returns (result, visited paths)."""
    from playwright.sync_api import sync_playwright
    visited = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()

        def handle(route):
            path = "/" + route.request.url.split("fake.test/", 1)[1].split("?")[0]
            visited.append(path)
            route.fulfill(body=f"<html><body>{pages.get(path, 'missing')}</body></html>", content_type="text/html")

        context.route("http://fake.test/**", handle)
        opener = context.new_page()
        opener.goto("http://fake.test/opener")
        with context.expect_page() as info:
            opener.evaluate(f"window.open('http://fake.test{start}', 'pp')")
        result = verifier.complete_paypal_popup(info.value, "sb-test@personal.example.com", "pw",
                                                timeout=timeout, require_sandbox=False)
        browser.close()
    return result, visited


def test_new_paypal_email_page_without_btnNext_id():
    """Regression: PayPal's newer 'Pay with PayPal' email page has a Next button without id=btnNext."""
    pages = {
        "/opener": "",
        "/email": '<h1>Pay with PayPal</h1><input id="email"><button onclick="location.href=\'/password\'">Next</button>',
        "/password": '<input id="password" type="password"><button id="btnLogin" onclick="location.href=\'/review\'">Log In</button>',
        "/review": '<button>Pay in 4</button><button onclick="window.close()">Complete Purchase</button>',
    }
    result, visited = _run_popup_on(pages, "/email")
    assert result == "" and "/password" in visited and "/review" in visited


def test_email_page_with_no_button_uses_enter():
    pages = {
        "/opener": "",
        "/email": '<form action="/password"><input id="email" name="e"></form>',
        "/password": '<input id="password" type="password"><button id="btnLogin" onclick="location.href=\'/review\'">Log In</button>',
        "/review": '<button onclick="window.close()">Pay</button>',
    }
    result, visited = _run_popup_on(pages, "/email")
    assert result == "" and "/password" in visited


def test_next_is_retried_if_first_click_is_ignored():
    pages = {
        "/opener": "",
        "/email": ('<input id="email"><button id="next">Next</button><script>let n=0;'
                   'document.getElementById("next").onclick=()=>{ if(++n>1) location.href="/password"; };</script>'),
        "/password": '<input id="password" type="password"><button id="btnLogin" onclick="location.href=\'/review\'">Log In</button>',
        "/review": '<button onclick="window.close()">Pay</button>',
    }
    result, visited = _run_popup_on(pages, "/email", timeout=30)
    assert result == "" and "/password" in visited


def test_first_paypal_click_ignored_then_retried(tmp_path, buyer, monkeypatch):
    """Regression: PayPal ignored the first click while its buttons were loading."""
    store = tmp_path / "slow_button_store"
    store.mkdir()
    slow = FAKE_STORE.replace(
        'document.querySelector("paypal-button").addEventListener("click", () => {',
        'let clicks = 0; document.querySelector("paypal-button").addEventListener("click", () => {'
        ' if (++clicks < 2) return;')
    assert slow != FAKE_STORE
    (store / "app.py").write_text(slow)
    port = free_port()
    url = start_store(store, port)
    monkeypatch.setattr(verifier, "OUTPUT_ROOT", tmp_path / "out")
    monkeypatch.setattr(verifier, "SANDBOX_HOST", "127.0.0.1")
    monkeypatch.setattr(verifier, "POPUP_OPEN_SECONDS", 3)
    monkeypatch.setattr(verifier, "_confirm_with_api",
                        lambda run, order_id: run.result.update(purchase_succeeded=True, order_status="COMPLETED"))
    try:
        result = verifier.verify_checkout(url)
    finally:
        stop_store(port)
    assert result["purchase_succeeded"], result
    assert "paypal_click_retry" in [s["name"] for s in result["steps"]]


def test_no_popup_after_retries_fails_cleanly(tmp_path, buyer, monkeypatch):
    store = tmp_path / "dead_button_store"
    store.mkdir()
    (store / "app.py").write_text(FAKE_STORE.replace("window.open(", "void ("))
    port = free_port()
    url = start_store(store, port)
    monkeypatch.setattr(verifier, "OUTPUT_ROOT", tmp_path / "out")
    monkeypatch.setattr(verifier, "POPUP_OPEN_SECONDS", 2)
    try:
        result = verifier.verify_checkout(url)
    finally:
        stop_store(port)
    assert result["error_code"] == "PAYPAL_POPUP_MISSING" and not result["purchase_succeeded"]


def test_compare_does_not_blame_store_for_verifier_problems():
    before = dict(verify_checkout_mock(label="before"), purchase_succeeded=False, error_code="PAYPAL_POPUP_TIMEOUT")
    after = verify_checkout_mock(label="after")
    changes = compare_runs(before, after)["changes"]
    assert not any("fixed a checkout" in c for c in changes)
    assert any("not a store problem" in c for c in changes)
    broken_store = dict(before, error_code="PAYPAL_BUTTON_MISSING")
    assert "The upgrade fixed a checkout that was failing." in compare_runs(broken_store, after)["changes"]
