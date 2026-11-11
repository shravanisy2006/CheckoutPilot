"""Findings are only made from pages the scanner really reached. Run: pytest tests/test_scanner_honesty.py -v"""

import asyncio
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ai_engine.rules import check_paypal_on_cart, check_paypal_on_product
from ai_engine.vision import select_screenshots


def _page(step, verified=True, paypal=False, viewport="desktop"):
    return {"step": step, "viewport": viewport, "verified": verified, "screenshot_path": "",
            "paypal_elements": [{"type": "paypal_button", "visible": True}] if paypal else []}


def test_unverified_cart_makes_no_finding():
    """Seen on real stores: Add to Cart not found -> empty /cart page -> false 'no PayPal on cart'."""
    scan = {"pages": [_page("cart", verified=False), _page("product", verified=False)]}
    assert check_paypal_on_cart(scan) == []
    assert check_paypal_on_product(scan) == []


def test_verified_cart_without_paypal_is_still_a_finding():
    scan = {"pages": [_page("cart", verified=True)]}
    assert [i["issue_id"] for i in check_paypal_on_cart(scan)] == ["no_paypal_on_cart"]


def test_old_scans_without_the_flag_still_work():
    scan = {"pages": [{"step": "cart", "viewport": "desktop", "paypal_elements": []}]}
    assert check_paypal_on_cart(scan)


def test_vision_skips_blank_or_unreached_pages(tmp_path):
    shot = tmp_path / "cart.png"
    shot.write_bytes(b"png")
    scan = {"pages": [
        {**_page("cart", verified=False), "screenshot_path": str(shot)},
        {**_page("checkout", verified=True), "screenshot_path": str(shot)},
    ]}
    paths, labels, _ = select_screenshots(scan)
    assert labels == ["checkout (desktop)"]


# ---------------------------------------------------- real browser, local pages ---
LATE_RENDER = """<!doctype html><html><body><div id=app></div><script>
setTimeout(function () { document.getElementById('app').innerHTML =
  '<h1>Fountain pen</h1><p>' + 'A lovely pen for everyday writing. '.repeat(4) + '</p>' +
  '<button id=add>Add to cart</button>'; }, 1500);
</script></body></html>"""


@pytest.fixture
def site(tmp_path):
    (tmp_path / "index.html").write_text(LATE_RENDER, encoding="utf-8")
    (tmp_path / "blank.html").write_text("<!doctype html><html><body></body></html>", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _evidence(url, step, reached=True):
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    from scanner.browser import BrowserConfig
    from scanner.navigator import StoreNavigator

    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            nav = StoreNavigator(page, BrowserConfig(screenshots_dir="outputs/_test_scanner_honesty"))
            await page.goto(url, wait_until="domcontentloaded")
            result = await nav.capture_page_evidence(step=step, viewport="desktop", reached=reached)
            await browser.close()
            return result

    return asyncio.run(run())


def test_waits_for_pages_that_render_late(site, monkeypatch):
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    ev = _evidence(site + "/index.html", "product")
    assert ev["blank"] is False and ev["verified"] is True and ev["text_chars"] >= 40


def test_blank_page_is_not_verified(site, monkeypatch):
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    ev = _evidence(site + "/blank.html", "cart")
    assert ev["blank"] is True and ev["verified"] is False
    assert any("blank" in w for w in ev["warnings"])


def test_not_reached_page_is_not_verified(site, monkeypatch):
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    ev = _evidence(site + "/index.html", "cart", reached=False)
    assert ev["verified"] is False


def test_wording_for_a_store_without_any_paypal():
    """Seen on a real practice shop: no PayPal anywhere, so don't claim PayPal is at checkout."""
    scan = {"detected_sdk_version": "unknown",
            "pages": [_page("cart"), _page("product"), _page("checkout")]}
    cart = check_paypal_on_cart(scan)[0]["evidence"]
    assert "does not seem to offer PayPal" in cart and "final checkout step" not in cart
    assert "does not seem to offer PayPal" in check_paypal_on_product(scan)[0]["evidence"]


def test_wording_when_paypal_is_at_checkout():
    scan = {"detected_sdk_version": "v5",
            "pages": [_page("cart"), _page("checkout", paypal=True)]}
    assert "final checkout step" in check_paypal_on_cart(scan)[0]["evidence"]
