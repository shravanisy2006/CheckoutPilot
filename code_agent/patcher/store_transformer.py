"""
Target store transformations: the built-in ("template") upgrade recipe.

It turns a v5 checkout into the same v6 checkout as demo_stores/upgraded_store, the reference
upgrade that has passed real PayPal Sandbox payments. Every step is guarded so it only changes
what it recognises and leaves everything else (catalogue, prices, form fields, ids) untouched.

v6 facts this relies on (developer.paypal.com/v5-v6):
  - SDK: <script async src=".../web-sdk/v6/core" onload=...>, no settings in the URL
  - paypal.createInstance({clientToken | clientId, components: ["paypal-payments"], pageType})
  - findEligibleMethods() -> createPayPalOneTimePaymentSession({onApprove, onCancel, onError})
  - session.start({presentationMode: "auto"}, createOrder())  (an order-id promise, not a function)
  - <paypal-button> starts hidden; the script shows it once PayPal is eligible
"""

import re

V6_SDK_TAG = (
    '  <!-- PayPal JavaScript SDK v6 -->\n'
    '  <script async src="{{PAYPAL_SDK_URL}}" onload="onPayPalWebSdkLoaded()" '
    'onerror="onPayPalWebSdkFailed()"></script>\n'
)
CLIENT_ID_META = '  <meta name="paypal-client-id" content="{{PAYPAL_CLIENT_ID}}">\n'
V5_SCRIPT = re.compile(
    r'[ \t]*(?:<!--[^\n]*SDK v5[^\n]*-->[ \t]*\n[ \t]*)?'
    r'<script[^>]+src=["\'][^"\']*paypal\.com/sdk/js[^"\']*["\'][^>]*>\s*</script>[ \t]*\n?',
    re.IGNORECASE,
)
# A synchronous SDK tag (no onload): v6 must load async and call onPayPalWebSdkLoaded() when ready.
SYNC_SDK_TAG = re.compile(
    r'[ \t]*(?:<!--[^\n]*SDK v5[^\n]*-->[ \t]*\n[ \t]*)?'
    r'<script\s+src=["\'](?:\{\{PAYPAL_SDK_URL\}\}|[^"\']*web-sdk/v6/core)["\']\s*>\s*</script>[ \t]*\n?')
CHECKOUT_DIV = re.compile(r'<div\s+class=["\']checkout(?: upgraded)?["\']>[ \t]*\n')
OLD_LAYOUT_NOTE = re.compile(r'[ \t]*<!--\s*Desktop: two columns.*?below the fold\.\s*-->[ \t]*\n', re.DOTALL)
NEW_LAYOUT_NOTE = ('    <!-- Upgrade: the summary + PayPal come first, so on mobile PayPal is visible without scrolling.\n'
                   '         On desktop CSS still places the summary on the right. -->\n')
ORDER_SUMMARY = re.compile(r'\n?([ \t]*<aside[^>]*id=["\']order-summary["\'][^>]*>.*?</aside>[ \t]*\n)', re.DOTALL)
CHECKOUT_RENDER = """  <script>
    (async function () {
      const total = await renderCartLines(document.getElementById("cart-lines"));
      document.getElementById("cart-total").textContent = "$" + total.toFixed(2);
      if (readCart().length === 0) document.getElementById("cart-empty").hidden = false;
    })();
  </script>
"""


def _add_client_id_meta(html: str) -> str:
    """The v6 script falls back to the public client ID if the client token fails."""
    if 'name="paypal-client-id"' in html:
        return html
    return re.sub(r'(<meta\s+name=["\']viewport["\'][^>]*>[ \t]*\n)', lambda m: m.group(1) + CLIENT_ID_META, html, count=1)


def _add_sdk_tag(html: str) -> str:
    if "onPayPalWebSdkLoaded" in html or "</body>" not in html:
        return html
    return html.replace("</body>", V6_SDK_TAG + "</body>", 1)


def patch_checkout_template(html: str) -> str:
    """Checkout page: v5 script out, v6 button + script in, summary + PayPal first on mobile."""
    html = V5_SCRIPT.sub("", html)
    html = SYNC_SDK_TAG.sub("", html)
    html = _add_client_id_meta(html)
    html = OLD_LAYOUT_NOTE.sub(NEW_LAYOUT_NOTE, html, count=1)

    # Mobile: put the order summary (with PayPal) BEFORE the long form in the page.
    # On desktop the CSS (.checkout.upgraded) still shows it on the right.
    match = CHECKOUT_DIV.search(html)
    summary = ORDER_SUMMARY.search(html)
    if match and summary and summary.start() > match.end():
        block = summary.group(1)
        html = html[:summary.start()] + "\n" + html[summary.end():]
        html = html[:match.end()] + block + "\n" + html[match.end():]
    html = re.sub(r'<div\s+class=["\']checkout["\']>', '<div class="checkout upgraded">', html, count=1)

    html = re.sub(
        r'<div id="paypal-button-container">\s*</div>',
        '<div id="paypal-button-container">\n          <paypal-button type="pay" hidden></paypal-button>\n        </div>',
        html, count=1)

    # The v5 checkout.js drew the cart lines AND the v5 buttons: replace it with the v6 script
    # plus the small cart-lines renderer it used to provide.
    if '<script src="/static/checkout.js"></script>' in html:
        html = html.replace('  <script src="/static/checkout.js"></script>\n',
                            '  <script src="/static/paypal.js"></script>\n' + CHECKOUT_RENDER, 1)
        html = html.replace('<script src="/static/checkout.js"></script>',
                            '<script src="/static/paypal.js"></script>\n' + CHECKOUT_RENDER, 1)
    return _add_sdk_tag(html)


def patch_cart_template(html: str) -> str:
    """Cart page: PayPal express checkout under the cart total (SDK v6)."""
    html = V5_SCRIPT.sub("", html)
    html = SYNC_SDK_TAG.sub("", html)
    html = _add_client_id_meta(html)
    if "<paypal-button" not in html and '<div class="actions"' in html:
        express = (
            '<!-- Upgrade: PayPal express checkout right on the cart page (SDK v6). -->\n'
            '      <div id="paypal-button-container" class="express">\n'
            '        <paypal-button type="pay" hidden></paypal-button>\n'
            '      </div>\n'
            '      <p id="order-status" role="status"></p>\n\n'
            '      <div class="actions"'
        )
        html = re.sub(r'<!--[^\n]*no PayPal button here[^\n]*-->\s*\n\s*', "", html, count=1, flags=re.IGNORECASE)
        html = html.replace('<div class="actions"', express, 1)
    if "/static/paypal.js" not in html and '<script src="/static/cart.js"></script>' in html:
        html = html.replace('<script src="/static/cart.js"></script>',
                            '<script src="/static/cart.js"></script>\n  <script src="/static/paypal.js"></script>', 1)
    # Hide the express button when the cart is empty (the page's own refresh() keeps it in sync).
    marker = 'document.getElementById("cart-empty").hidden = !empty;'
    if marker in html and 'getElementById("paypal-button-container").hidden' not in html:
        html = html.replace(marker, marker + '\n      document.getElementById("paypal-button-container").hidden = empty;', 1)
    return _add_sdk_tag(html)


UPGRADE_CSS = """
/* Upgrade (CheckoutPilot): v6 PayPal button + order summary first on mobile, right-hand column on desktop. */
#paypal-button-container paypal-button { display: block; width: 100%; }
#paypal-button-container paypal-button[hidden] { display: none; }
.express { max-width: 420px; }
.checkout.upgraded { grid-template-areas: "form summary"; }
.checkout.upgraded #order-summary { grid-area: summary; }
.checkout.upgraded #shipping-form { grid-area: form; }
@media (max-width: 760px) {
  .checkout.upgraded { grid-template-areas: "summary" "form"; }
}
"""


def patch_style_css(css: str) -> str:
    """Add the upgrade rules at the end, as one self-contained block (never edits existing rules)."""
    if ".checkout.upgraded" in css:
        return css
    return css.rstrip("\n") + "\n" + UPGRADE_CSS


def patch_app_routes(code: str) -> str:
    """Add client-token endpoint and SDK URL replacement to app.py.

    Each step checks for itself, so an earlier (e.g. AI) edit that already added one part
    never makes the others get skipped.
    """

    # 1. Define SANDBOX_SDK_URL if not present
    if "SANDBOX_SDK_URL" not in code:
        code = code.replace(
            'CURRENCY = "USD"',
            'CURRENCY = "USD"\nSANDBOX_SDK_URL = "https://www.sandbox.paypal.com/web-sdk/v6/core"',
        )

    # 2. Add SDK URL replacement to render()
    if '{{PAYPAL_SDK_URL}}' not in code and 'html = html.replace("{{CURRENCY}}", CURRENCY)' in code:
        code = code.replace(
            'html = html.replace("{{CURRENCY}}", CURRENCY)',
            'html = html.replace("{{CURRENCY}}", CURRENCY)\n    html = html.replace("{{PAYPAL_SDK_URL}}", SANDBOX_SDK_URL)',
        )

    # 3. Update health check SDK version to v6
    code = code.replace('"paypal_sdk": "v5"', '"paypal_sdk": "v6"')

    # 4. Insert client_token endpoint before /api/orders
    endpoint_code = (
        '@app.get("/api/paypal/client-token")\n'
        'def client_token() -> dict:\n'
        '    """Short-lived, browser-safe token the v6 SDK needs. The secret never leaves the server."""\n'
        '    client = _paypal_client()\n'
        '    try:\n'
        '        token = client.get_client_token()\n'
        '    except Exception as error:\n'
        '        code = getattr(error, "code", "PAYPAL_ERROR")\n'
        '        message = getattr(error, "message", str(error))\n'
        '        raise HTTPException(status_code=502, detail=f"{code}: {message}") from error\n'
        '    if not token:\n'
        '        raise HTTPException(status_code=503, detail="PayPal client returned no client token.")\n'
        '    return {"accessToken": token}\n\n\n'
    )

    if "/api/paypal/client-token" in code:
        return code
    if '@app.post("/api/orders")' in code:
        code = code.replace('@app.post("/api/orders")', endpoint_code + '@app.post("/api/orders")', 1)
    else:
        code = code + "\n\n" + endpoint_code

    return code


def get_paypal_v6_js() -> str:
    """The v6 browser script: identical to demo_stores/upgraded_store/static/paypal.js (Sandbox-verified)."""
    return PAYPAL_V6_JS


PAYPAL_V6_JS = """// Inkwell & Co. (upgraded) - PayPal JavaScript SDK v6 one-time payment.
// Used on the cart page (express checkout) and the checkout page.
// The server works out the price; the browser only sends item IDs and quantities.

function showStatus(message, kind) {
  const box = document.getElementById("order-status");
  if (!box) return;
  box.textContent = message;
  box.className = kind || "";
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || ("Request failed (" + response.status + ")"));
  }
  return data;
}

// v6 needs a browser-safe client token from our server (the secret stays on the server).
// If that fails, fall back to the public client ID.
async function getSdkAuth() {
  try {
    const response = await fetch("/api/paypal/client-token");
    if (response.ok) {
      const data = await response.json();
      if (data.accessToken) return { clientToken: data.accessToken };
    }
  } catch (error) { /* fall through */ }
  const meta = document.querySelector('meta[name="paypal-client-id"]');
  return { clientId: meta ? meta.content : "" };
}

// The SDK wants a Promise that resolves to { orderId }.
async function createOrder() {
  const order = await postJson("/api/orders", { items: readCart() });
  return { orderId: order.id };
}

async function captureAndFinish(orderId) {
  showStatus("Capturing payment...");
  const result = await postJson("/api/orders/" + encodeURIComponent(orderId) + "/capture");
  if (result.status !== "COMPLETED") {
    showStatus("Payment not completed (status: " + result.status + "). Please try again.", "error");
    return;
  }
  clearCart();
  window.location.href = "/success?order=" + encodeURIComponent(result.id);
}

async function setUpPayPal() {
  if (readCart().length === 0) return;  // nothing to pay for
  const sdkInstance = await window.paypal.createInstance({
    ...(await getSdkAuth()),
    components: ["paypal-payments"],
    pageType: "checkout",
  });

  const methods = await sdkInstance.findEligibleMethods({ currencyCode: "USD" });
  if (!methods.isEligible("paypal")) {
    showStatus("PayPal is not available for this purchase.", "error");
    return;
  }

  const session = sdkInstance.createPayPalOneTimePaymentSession({
    onApprove: async function (data) {
      try {
        await captureAndFinish(data.orderId);
      } catch (error) {
        showStatus("Payment failed: " + error.message, "error");
      }
    },
    onCancel: function () {
      showStatus("Payment cancelled. Your cart is still saved.");
    },
    onError: function (error) {
      showStatus("Payment failed: " + (error && error.message ? error.message : error), "error");
    },
  });

  const button = document.querySelector("#paypal-button-container paypal-button");
  button.removeAttribute("hidden");
  button.addEventListener("click", async function () {
    showStatus("");
    try {
      await session.start({ presentationMode: "auto" }, createOrder());
    } catch (error) {
      showStatus("Payment failed: " + error.message, "error");
    }
  });
}

// Called by the SDK <script> tag's onload / onerror.
function onPayPalWebSdkLoaded() {
  setUpPayPal().catch((error) => showStatus("PayPal could not start: " + error.message, "error"));
}

function onPayPalWebSdkFailed() {
  showStatus("PayPal could not load. Check your internet connection.", "error");
}
"""
