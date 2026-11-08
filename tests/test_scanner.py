"""
Unit and integration tests for CheckoutPilot Scanner module.

Covers:
 1. Valid store URL
 2. Invalid URL
 3. Unsupported URL scheme
 4. Successful browser launch
 5. Browser cleanup after errors
 6. Product -> cart -> checkout navigation
 7. Missing Add to Cart button
 8. Missing checkout button
 9. PayPal script detection
10. SDK version detection
11. PayPal element detection
12. Desktop scan
13. Mobile scan
14. Screenshot generation
15. JSON serialization of scanner output
16. Navigation timeout handling
"""

import asyncio
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from scanner import (
    BrowserConfig,
    InvalidURLError,
    NavigationSelectors,
    PlaywrightBrowserSession,
    async_scan_store,
    detect_overall_sdk_version,
    detect_paypal_elements,
    detect_paypal_scripts,
    detect_paypal_sdk_version,
    filter_paypal_scripts,
    is_paypal_script,
    is_valid_url,
    parse_script_details,
    scan_store,
    validate_url,
)


# =============================================================================
# Local Test Server Fixture (Deterministic, 100% Offline, Thread-Safe)
# =============================================================================

class MockStoreHandler(BaseHTTPRequestHandler):
    """Configurable mock e-commerce store handler for offline testing."""

    missing_add_to_cart: bool = False
    missing_checkout: bool = False
    simulate_slow: bool = False

    def do_GET(self):
        if self.simulate_slow or "slow=true" in self.path:
            time.sleep(1.0)

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        # Product page
        if not any(p in self.path for p in ("/cart", "/checkout")):
            add_to_cart_btn = (
                ""
                if self.missing_add_to_cart
                else '<button id="add-to-cart">Add to Cart</button>'
            )

            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Demo Store - Product Page</title>
    <script src="https://www.paypal.com/sdk/js?client-id=test_client_id&components=buttons,messages"></script>
</head>
<body>
    <h1>Wireless Headphones</h1>
    <p>$149.99</p>
    <div data-pp-message data-pp-amount="149.99" class="paypal-msg">Pay in 4 interest-free payments</div>
    {add_to_cart_btn}
    <a id="go-to-cart" href="/cart">View Cart</a>
    <div id="paypal-button-container" style="width:250px; height:45px; margin-top:10px;"></div>
</body>
</html>"""

        # Cart page
        elif "/cart" in self.path:
            checkout_btn = (
                ""
                if self.missing_checkout
                else '<a id="go-to-checkout" href="/checkout">Proceed to Checkout</a>'
            )

            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Demo Store - Cart</title>
</head>
<body>
    <h1>Shopping Cart</h1>
    <p>1 item</p>
    {checkout_btn}
    <div id="paypal-button-container" style="width:250px; height:45px; margin-top:10px;"></div>
</body>
</html>"""

        # Checkout page
        elif "/checkout" in self.path:
            html = """<!DOCTYPE html>
<html>
<head>
    <title>Demo Store - Checkout</title>
    <script src="https://www.paypal.com/sdk/js?client-id=test_client_id&components=buttons"></script>
</head>
<body>
    <h1>Checkout Page</h1>
    <div id="paypal-button-container" style="width:300px; height:50px;"></div>
</body>
</html>"""

        else:
            html = "<html><body>Not Found</body></html>"

        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress HTTP server noise in test output


@pytest.fixture(scope="session")
def demo_server_url():
    """Spin up an ephemeral local HTTP server on a free port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockStoreHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()


@pytest.fixture
def localhost_scan_enabled(monkeypatch):
    """Allow localhost scanning for tests that use the local demo server."""
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")


@pytest.fixture
def fast_config():
    """Fast timeout configuration to keep test runs rapid and deterministic."""
    return BrowserConfig(
        headless=True,
        timeout_ms=10000,
        navigation_timeout_ms=3000,
        action_timeout_ms=500,
        screenshots_dir="screenshots",
    )


# =============================================================================
# 1. Valid Store URL
# =============================================================================

def test_valid_store_url(monkeypatch):
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    assert validate_url("https://example.com") == "https://example.com"
    assert validate_url("  http://localhost:8000/shop  ") == "http://localhost:8000/shop"
    assert validate_url("https://sub.domain.store.co.uk/item?id=1") == "https://sub.domain.store.co.uk/item?id=1"
    assert is_valid_url("https://example.com") is True
    assert is_valid_url("http://127.0.0.1:3000") is True


# =============================================================================
# 2. Invalid URL
# =============================================================================

def test_invalid_url():
    with pytest.raises(InvalidURLError):
        validate_url("")
    with pytest.raises(InvalidURLError):
        validate_url("   ")
    with pytest.raises(InvalidURLError):
        validate_url(None)
    with pytest.raises(InvalidURLError):
        validate_url("not-a-valid-url")
    with pytest.raises(InvalidURLError):
        validate_url("http://")
    with pytest.raises(InvalidURLError):
        validate_url("https://")
    assert is_valid_url("") is False
    assert is_valid_url("not-a-valid-url") is False


# =============================================================================
# 3. Unsupported URL Scheme
# =============================================================================

def test_unsupported_url_scheme():
    with pytest.raises(InvalidURLError) as exc_ftp:
        validate_url("ftp://files.example.com")
    assert "Unsupported scheme 'ftp'" in str(exc_ftp.value)

    with pytest.raises(InvalidURLError) as exc_js:
        validate_url("javascript:alert(1)")
    assert "Unsupported scheme 'javascript'" in str(exc_js.value)

    with pytest.raises(InvalidURLError) as exc_file:
        validate_url("file:///etc/passwd")
    assert "Unsupported scheme 'file'" in str(exc_file.value)

    assert is_valid_url("ftp://example.com") is False
    assert is_valid_url("javascript:void(0)") is False


# =============================================================================
# 3b. SSRF Protection (private / loopback / link-local / multicast / reserved)
# =============================================================================

def test_ssrf_private_ipv4_always_blocked(monkeypatch):
    """Private IPv4 addresses must always be blocked, even with localhost flag."""
    monkeypatch.setattr("scanner.url_validator.ALLOW_LOCALHOST_SCANS", True)
    for host in ("10.0.0.1", "10.255.255.254", "172.16.0.1", "172.31.255.254", "192.168.0.1", "192.168.255.254"):
        with pytest.raises(InvalidURLError):
            validate_url(f"http://{host}/")
        assert is_valid_url(f"http://{host}/") is False


def test_ssrf_private_ipv4_blocked_by_default():
    """Private IPv4 addresses blocked when ALLOW_LOCALHOST_SCANS is false (default)."""
    for host in ("10.0.0.1", "172.16.0.1", "192.168.1.1"):
        with pytest.raises(InvalidURLError):
            validate_url(f"http://{host}/")
        assert is_valid_url(f"http://{host}/") is False


def test_ssrf_loopback_blocked_by_default():
    """Loopback addresses blocked when ALLOW_LOCALHOST_SCANS is false (default)."""
    for host in ("127.0.0.1", "127.255.255.254", "localhost"):
        with pytest.raises(InvalidURLError):
            validate_url(f"http://{host}/")
        assert is_valid_url(f"http://{host}/") is False
    # IPv6 loopback must use bracketed format in URLs
    with pytest.raises(InvalidURLError):
        validate_url("http://[::1]/")
    assert is_valid_url("http://[::1]/") is False


def test_ssrf_loopback_allowed_with_flag(monkeypatch):
    """Loopback addresses allowed only when ALLOW_LOCALHOST_SCANS=true."""
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    for host in ("127.0.0.1", "127.255.255.254", "localhost"):
        assert validate_url(f"http://{host}/") == f"http://{host}/"
        assert is_valid_url(f"http://{host}/") is True
    # IPv6 loopback must use bracketed format in URLs
    assert validate_url("http://[::1]/") == "http://[::1]/"
    assert is_valid_url("http://[::1]/") is True


def test_ssrf_link_local_always_blocked(monkeypatch):
    """Cloud metadata / link-local always blocked, even with localhost flag."""
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    with pytest.raises(InvalidURLError):
        validate_url("http://169.254.169.254/")
    assert is_valid_url("http://169.254.169.254/") is False


def test_ssrf_multicast_always_blocked(monkeypatch):
    """Multicast always blocked, even with localhost flag."""
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    with pytest.raises(InvalidURLError):
        validate_url("http://224.0.0.1/")
    assert is_valid_url("http://224.0.0.1/") is False


def test_ssrf_ipv6_private_always_blocked(monkeypatch):
    """Private IPv6 addresses always blocked, even with localhost flag."""
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    for host in ("fc00::1", "fd00::1", "fe80::1"):
        with pytest.raises(InvalidURLError):
            validate_url(f"http://[{host}]/")
        assert is_valid_url(f"http://[{host}]/") is False


def test_ssrf_ipv6_loopback_allowed_with_flag(monkeypatch):
    """IPv6 loopback (::1) allowed when ALLOW_LOCALHOST_SCANS=true."""
    monkeypatch.setenv("ALLOW_LOCALHOST_SCANS", "true")
    assert validate_url("http://[::1]/") == "http://[::1]/"
    assert is_valid_url("http://[::1]/") is True


def test_ssrf_public_urls_allowed():
    """Public domains allowed with default flag."""
    for host in ("example.com", "sub.domain.store.co.uk", "www.paypal.com", "paypalobjects.com"):
        assert validate_url(f"https://{host}/") == f"https://{host}/"
        assert is_valid_url(f"https://{host}/") is True


def test_ssrf_flag_defaults_to_false():
    """ALLOW_LOCALHOST_SCANS defaults to false in production."""
    import scanner.url_validator as uv
    assert uv.ALLOW_LOCALHOST_SCANS is False


def test_successful_browser_launch(fast_config):
    async def _test():
        async with PlaywrightBrowserSession(config=fast_config) as session:
            assert session.browser is not None
            assert session.browser.is_connected()
            # Verify single-browser desktop and mobile context creation
            d_ctx = await session.create_desktop_context()
            m_ctx = await session.create_mobile_context()
            assert d_ctx is not None
            assert m_ctx is not None
            await d_ctx.close()
            await m_ctx.close()
        # Verify diagnostic helper
        ready = await PlaywrightBrowserSession.verify_browser(config=fast_config)
        assert ready is True

    asyncio.run(_test())


# =============================================================================
# 5. Browser Cleanup After Errors
# =============================================================================

def test_browser_cleanup_after_errors(fast_config):
    async def _test():
        session = PlaywrightBrowserSession(config=fast_config)
        with pytest.raises(ZeroDivisionError):
            async with session:
                assert session.browser.is_connected()
                _ = 1 / 0  # Simulate unhandled exception

        # Verify resources were cleaned up despite the exception
        assert session._browser is None
        assert session._playwright is None

    asyncio.run(_test())


# =============================================================================
# 6. Product -> Cart -> Checkout Navigation
# =============================================================================

def test_product_cart_checkout_navigation(demo_server_url, localhost_scan_enabled, fast_config):
    result = scan_store(demo_server_url, include_mobile=False, config=fast_config)

    assert result["store_url"] == demo_server_url
    assert result["status"] == "completed"
    assert result["navigation_summary"]["desktop"] == {
        "product": True,
        "cart": True,
        "checkout": True,
    }
    assert len(result["pages"]) == 3
    steps = [p["step"] for p in result["pages"]]
    assert steps == ["product", "cart", "checkout"]


# =============================================================================
# 7. Missing Add to Cart Button
# =============================================================================

def test_missing_add_to_cart_button(demo_server_url, localhost_scan_enabled, fast_config):
    MockStoreHandler.missing_add_to_cart = True
    try:
        result = scan_store(demo_server_url, include_mobile=False, config=fast_config)
        assert result["store_url"] == demo_server_url
        assert len(result["pages"]) == 3
        # Warning recorded about missing Add to Cart button
        assert any("Add to Cart button" in w for w in result["warnings"])
        cart_page = next(p for p in result["pages"] if p["step"] == "cart")
        assert any("Add to Cart button" in w for w in cart_page.get("warnings", []))
    finally:
        MockStoreHandler.missing_add_to_cart = False


# =============================================================================
# 8. Missing Checkout Button
# =============================================================================

def test_missing_checkout_button(demo_server_url, localhost_scan_enabled, fast_config):
    MockStoreHandler.missing_checkout = True
    try:
        result = scan_store(demo_server_url, include_mobile=False, config=fast_config)
        assert result["store_url"] == demo_server_url
        assert len(result["pages"]) == 3
        # Warning recorded about missing Go to Checkout button
        assert any("Checkout button" in w for w in result["warnings"])
        checkout_page = next(p for p in result["pages"] if p["step"] == "checkout")
        assert any("Checkout button" in w for w in checkout_page.get("warnings", []))
    finally:
        MockStoreHandler.missing_checkout = False


# =============================================================================
# 9. PayPal Script Detection
# =============================================================================

def test_paypal_script_detection():
    scripts = [
        "https://www.paypal.com/sdk/js?client-id=abc",
        "https://www.paypalobjects.com/api/checkout.js",
        "https://www.paypal.com/tagmanager/pptm.js?id=123",
        "https://cdn.example.com/main.js",
        "https://analytics.google.com/analytics.js",
    ]

    filtered = filter_paypal_scripts(scripts)
    assert len(filtered) == 3
    assert "https://cdn.example.com/main.js" not in filtered
    assert "https://analytics.google.com/analytics.js" not in filtered

    assert is_paypal_script("https://www.paypal.com/sdk/js") is True
    assert is_paypal_script("https://cdn.jsdelivr.net/npm/jquery.js") is False

    details = parse_script_details("https://www.paypal.com/sdk/js?client-id=test&components=buttons,messages")
    assert details["is_paypal"] is True
    assert details["sdk_version"] == "v5"
    assert "messages" in details["components"]
    assert "buttons" in details["components"]


# =============================================================================
# 10. SDK Version Detection
# =============================================================================

def test_sdk_version_detection():
    # v4 legacy checkout.js
    assert detect_overall_sdk_version(["https://www.paypalobjects.com/api/checkout.js"]) == "v4"

    # v5 JS SDK
    assert detect_overall_sdk_version(["https://www.paypal.com/sdk/js?client-id=test"]) == "v5"

    # v6 Web SDK
    assert detect_overall_sdk_version(["https://www.paypal.com/web-sdk/v6/core"]) == "v6"

    # Unknown when not a recognized SDK version
    assert detect_overall_sdk_version(["https://www.paypal.com/tagmanager/pptm.js?id=xyz"]) == "unknown"

    # Unknown when no PayPal scripts at all (does not guess)
    assert detect_overall_sdk_version(["https://cdn.example.com/bundle.js"]) == "unknown"
    assert detect_overall_sdk_version([]) == "unknown"

    # Helper alias in scanner
    assert detect_paypal_sdk_version(["https://www.paypal.com/sdk/js?client-id=test"]) == "v5"


# =============================================================================
# 10b. PayPal False Positive Protection
# =============================================================================

def test_paypal_false_positive_subdomain():
    """paypal.evil.com should NOT be detected as PayPal (substring matching removed)."""
    assert is_paypal_script("https://paypal.evil.com/sdk.js") is False
    assert is_paypal_script("https://notpaypal.com/sdk.js") is False
    assert is_paypal_script("https://mypaypal-evil.com/sdk.js") is False


def test_paypal_false_positive_path():
    """evil.com/paypal/sdk.js should NOT be detected as PayPal."""
    assert is_paypal_script("https://evil.com/paypal/sdk.js") is False
    assert is_paypal_script("https://example.com/paypalments.js") is False


def test_paypal_false_positive_query():
    """Query string containing 'paypal' should not trigger detection on non-PayPal host."""
    assert is_paypal_script("https://cdn.example.com/script.js?x=paypal") is False


def test_paypal_legitimate_subdomains():
    """Legitimate PayPal subdomains should still be detected."""
    assert is_paypal_script("https://www.paypal.com/sdk/js") is True
    assert is_paypal_script("https://paypalobjects.com/api/checkout.js") is True
    assert is_paypal_script("https://api.paypal.com/v1/") is True
    assert is_paypal_script("https://api-m.sandbox.paypal.com/v1/") is True
    assert is_paypal_script("https://braintreegateway.com") is True


def test_paypal_non_paypal_domains():
    """Non-PayPal domains containing 'paypal' substring should not match."""
    assert is_paypal_script("https://mypaypalstore.com/checkout.js") is False
    assert is_paypal_script("https://paypal-clone.example.com/sdk.js") is False


# =============================================================================
# 11. PayPal Element Detection
# =============================================================================

def test_paypal_element_detection(demo_server_url, localhost_scan_enabled, fast_config):
    result = scan_store(demo_server_url, include_mobile=False, config=fast_config)
    product_page = next(p for p in result["pages"] if p["step"] == "product")

    elements = product_page["paypal_elements"]
    assert len(elements) > 0

    # Verify #paypal-button-container detection
    container = next((e for e in elements if e["id"] == "paypal-button-container"), None)
    assert container is not None
    assert container["visible"] is True
    assert container["bounding_box"] is not None
    assert container["bounding_box"]["width"] > 0
    assert container["bounding_box"]["height"] > 0

    # Verify Pay Later messaging detection
    messaging = product_page["pay_later_messaging"]
    assert messaging["detected"] is True
    assert messaging["elements_count"] >= 1
    assert messaging["script_component_present"] is True


# =============================================================================
# 12. Desktop Scan
# =============================================================================

def test_desktop_scan(demo_server_url, localhost_scan_enabled, fast_config):
    result = scan_store(demo_server_url, include_mobile=False, config=fast_config)

    assert "desktop" in result["navigation_summary"]
    assert "mobile" not in result["navigation_summary"]
    assert len(result["pages"]) == 3
    for p in result["pages"]:
        assert p["viewport"] == "desktop"
        assert p["url"].startswith("http://127.0.0.1")
        assert len(p["title"]) > 0


# =============================================================================
# 13. Mobile Scan
# =============================================================================

def test_mobile_scan(demo_server_url, localhost_scan_enabled, fast_config):
    result = scan_store(demo_server_url, include_mobile=True, config=fast_config)

    assert "desktop" in result["navigation_summary"]
    assert "mobile" in result["navigation_summary"]
    assert len(result["pages"]) == 6  # 3 desktop + 3 mobile

    mobile_pages = [p for p in result["pages"] if p["viewport"] == "mobile"]
    assert len(mobile_pages) == 3

    for p in mobile_pages:
        assert p["viewport"] == "mobile"
        assert p["success"] is True
        for elem in p["paypal_elements"]:
            assert "visible" in elem
            if elem["visible"]:
                assert elem["bounding_box"] is not None


# =============================================================================
# 14. Screenshot Generation
# =============================================================================

def test_screenshot_generation(demo_server_url, localhost_scan_enabled, fast_config):
    result = scan_store(demo_server_url, include_mobile=False, config=fast_config)

    for page in result["pages"]:
        screenshot_path = page["screenshot_path"]
        assert len(screenshot_path) > 0
        assert os.path.exists(screenshot_path)
        assert screenshot_path.endswith(".png")
        assert os.path.getsize(screenshot_path) > 0


# =============================================================================
# 15. JSON Serialization of Scanner Output
# =============================================================================

def test_json_serialization_of_output(demo_server_url, localhost_scan_enabled, fast_config):
    result = scan_store(demo_server_url, include_mobile=True, config=fast_config)

    serialized = json.dumps(result, indent=2)
    assert len(serialized) > 0

    deserialized = json.loads(serialized)
    assert deserialized["store_url"] == result["store_url"]
    assert deserialized["status"] == result["status"]
    assert len(deserialized["pages"]) == len(result["pages"])


# =============================================================================
# 16. Navigation Timeout Handling
# =============================================================================

def test_navigation_timeout_handling(demo_server_url, localhost_scan_enabled):
    # Set an aggressively low timeout to trigger navigation timeout on the slow route
    timeout_config = BrowserConfig(
        headless=True,
        timeout_ms=2000,
        navigation_timeout_ms=300,  # 300ms timeout
        action_timeout_ms=200,
        screenshots_dir="screenshots",
    )
    MockStoreHandler.simulate_slow = True
    try:
        result = scan_store(demo_server_url, include_mobile=False, config=timeout_config)
        assert result["status"] == "failed"
        assert len(result["errors"]) > 0
        assert any("Timeout" in err or "timed out" in err for err in result["errors"])
        first_page = result["pages"][0]
        assert first_page["success"] is False
        assert len(first_page["error"]) > 0
    finally:
        MockStoreHandler.simulate_slow = False


# =============================================================================
# 17. Malicious Redirect Protection
# =============================================================================

def test_malicious_redirect_target_blocked():
    """Redirect targets resolving to private IPs should be blocked at validation."""
    # A URL that would redirect to a private IP is rejected at the entry point.
    with pytest.raises(InvalidURLError):
        validate_url("http://169.254.169.254/")
    with pytest.raises(InvalidURLError):
        validate_url("http://10.0.0.1/")
    with pytest.raises(InvalidURLError):
        validate_url("http://127.0.0.1:8000/")


def test_legitimate_public_redirect_allowed():
    """Public domain redirects should still be allowed at URL validation."""
    assert validate_url("https://example.com/") == "https://example.com/"
    assert validate_url("https://www.paypal.com/checkout") == "https://www.paypal.com/checkout"


def test_redirect_to_private_ip_rejected():
    """Simulate a redirect chain: initial URL is public but target is private."""
    # validate_url only checks the initial URL; route blocking in navigator
    # catches redirects at the browser level. Here we verify the entry point
    # rejects private IP targets directly.
    for target in ("http://169.254.169.254/latest/meta-data/",
                   "http://10.0.0.1/admin",
                   "http://127.0.0.1:8000/internal"):
        with pytest.raises(InvalidURLError):
            validate_url(target)


# =============================================================================
# 18. Route Registration and Navigation Protection
# =============================================================================

def test_route_registration_is_async():
    """Page.route() must be awaited via async_init(), not called synchronously in __init__."""
    from unittest.mock import MagicMock, AsyncMock
    from scanner.navigator import StoreNavigator, BrowserConfig

    mock_page = MagicMock()
    mock_page.route = AsyncMock()

    nav = StoreNavigator(mock_page, config=BrowserConfig())
    assert nav._route_registered is False
    # Page.route should NOT have been called in __init__ (it's async)
    mock_page.route.assert_not_called()

    # After async_init, route should be registered and awaited
    asyncio.run(nav.async_init())
    mock_page.route.assert_awaited_once_with("**/*", nav._block_private_route)
    assert nav._route_registered is True


def test_route_blocks_private_ip_redirect():
    """Route handler aborts navigation to private/reserved IP addresses."""
    from unittest.mock import MagicMock, AsyncMock
    from scanner.navigator import StoreNavigator, BrowserConfig
    import ipaddress

    mock_page = MagicMock()
    nav = StoreNavigator(mock_page, config=BrowserConfig())

    # Create mock route and request with AsyncMock async methods
    mock_route = MagicMock()
    mock_route.abort = AsyncMock()
    mock_route.continue_ = AsyncMock()
    mock_request = MagicMock()

    # Private IPv4 redirect target should be aborted
    mock_request.url = "http://169.254.169.254/latest/meta-data/"
    asyncio.run(nav._block_private_route(mock_route, mock_request))
    mock_route.abort.assert_called_once()
    mock_route.continue_.assert_not_called()

    # Public domain redirect target should continue
    mock_route.abort.reset_mock()
    mock_route.continue_.reset_mock()
    mock_request.url = "https://www.paypal.com/checkout"
    asyncio.run(nav._block_private_route(mock_route, mock_request))
    mock_route.continue_.assert_called_once()
    mock_route.abort.assert_not_called()

    # Localhost redirect target should be aborted (navigator blocks all non-public IPs)
    mock_route.abort.reset_mock()
    mock_route.continue_.reset_mock()
    mock_request.url = "http://127.0.0.1:8000/internal"
    asyncio.run(nav._block_private_route(mock_route, mock_request))
    mock_route.abort.assert_called_once()
    mock_route.continue_.assert_not_called()
