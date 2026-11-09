"""
Target store transformations: applies clean, non-destructive upgrades
to templates, JavaScript, CSS, and Python routes.
"""

import re


def patch_checkout_template(html: str) -> str:
    """Upgrade checkout.html to use SDK v6 script, custom button element, and mobile layout class."""
    # 1. Upgrade SDK script tag to v6
    v5_script = re.compile(
        r'<script[^>]+src=["\'][^"\']*paypal\.com/sdk/js[^"\']*["\'][^>]*></script>',
        re.IGNORECASE,
    )
    if v5_script.search(html):
        html = v5_script.sub('  <script src="{{PAYPAL_SDK_URL}}"></script>', html)

    # 2. Add upgraded class to checkout grid
    html = re.sub(
        r'<div\s+class=["\']checkout["\']>',
        '<div class="checkout upgraded">',
        html,
        count=1,
    )

    # 3. Upgrade button container to include custom <paypal-button>
    legacy_container = '<div id="paypal-button-container"></div>'
    upgraded_container = (
        '<div id="paypal-button-container">\n'
        '        <paypal-button id="paypal-button" type="pay" hidden></paypal-button>\n'
        '      </div>'
    )
    if legacy_container in html:
        html = html.replace(legacy_container, upgraded_container)

    # 4. Swap static script from checkout.js to paypal.js
    html = html.replace('<script src="/static/checkout.js"></script>', '<script src="/static/paypal.js"></script>')

    return html


def patch_cart_template(html: str) -> str:
    """Add express checkout to cart.html."""
    # 1. Add paypal-client-id meta tag in head if missing
    if '<meta name="paypal-client-id"' not in html:
        html = html.replace(
            '<title>Your cart',
            '<meta name="paypal-client-id" content="{{PAYPAL_CLIENT_ID}}">\n  <title>Your cart',
        )

    # 2. Add express button before actions
    if '<paypal-button' not in html and '<div class="actions"' in html:
        express_block = (
            '      <!-- Upgrade: PayPal express checkout right on the cart page (SDK v6). -->\n'
            '      <div id="paypal-button-container" class="express">\n'
            '        <paypal-button type="pay" hidden></paypal-button>\n'
            '      </div>\n'
            '      <p id="order-status" role="status"></p>\n\n'
            '      <div class="actions"'
        )
        html = html.replace('<div class="actions"', express_block, 1)

    # 3. Add paypal.js script
    if '/static/paypal.js' not in html and '<script src="/static/cart.js"></script>' in html:
        html = html.replace(
            '<script src="/static/cart.js"></script>',
            '<script src="/static/cart.js"></script>\n  <script src="/static/paypal.js"></script>',
        )

    return html


def patch_style_css(css: str) -> str:
    """Add responsive grid template areas to style.css for above-the-fold mobile button."""
    if ".checkout.upgraded" in css:
        return css

    rules = (
        "\n/* Upgraded checkout: summary is first on mobile, but on the right on desktop. */\n"
        '.checkout.upgraded { grid-template-areas: "form summary"; }\n'
        ".checkout.upgraded #order-summary { grid-area: summary; }\n"
        ".checkout.upgraded #shipping-form { grid-area: form; }\n"
    )

    # Insert before media queries or at end
    if "@media (max-width: 760px)" in css:
        parts = css.split("@media (max-width: 760px)")
        media_block = (
            "@media (max-width: 760px) {\n"
            '  .checkout.upgraded { grid-template-areas: "summary" "form"; }'
        )
        css = parts[0] + rules + media_block + parts[1].replace("@media (max-width: 760px) {", "", 1)
    else:
        css = css + rules

    return css


def patch_app_routes(code: str) -> str:
    """Add client-token endpoint and SDK URL replacement to app.py."""
    if "/api/paypal/client-token" in code:
        return code

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

    if '@app.post("/api/orders")' in code:
        code = code.replace('@app.post("/api/orders")', endpoint_code + '@app.post("/api/orders")', 1)
    else:
        code = code + "\n\n" + endpoint_code

    return code


def get_paypal_v6_js() -> str:
    """Return the client-side PayPal v6 SDK integration script."""
    return """// Inkwell & Co. - checkout and cart integration using PayPal JavaScript SDK v6.
// Uses one-time payment sessions and web components (<paypal-button>).

const statusBox = document.getElementById("order-status");

function showStatus(message, kind) {
  if (!statusBox) return;
  statusBox.textContent = message;
  statusBox.className = kind || "";
}

async function fetchClientToken() {
  const resp = await fetch("/api/paypal/client-token");
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || ("Client token failed (" + resp.status + ")"));
  }
  const data = await resp.json();
  return data.accessToken;
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

async function initPayPalV6() {
  const clientToken = await fetchClientToken();
  if (!window.paypal || !window.paypal.createInstance) {
    return;
  }

  const instance = await window.paypal.createInstance({
    clientToken: clientToken,
    components: ["buttons"],
  });

  const session = await instance.createPayPalOneTimePaymentSession({
    onApprove: async function (data) {
      showStatus("Capturing payment...");
      const result = await postJson("/api/orders/" + encodeURIComponent(data.orderID) + "/capture");
      if (result.status !== "COMPLETED") {
        showStatus("Payment not completed (status: " + result.status + ").", "error");
        return;
      }
      if (typeof clearCart === "function") clearCart();
      window.location.href = "/success?order=" + encodeURIComponent(result.id);
    },
    onCancel: function () {
      showStatus("Payment cancelled. Cart saved.");
    },
    onError: function (err) {
      showStatus("Payment error: " + (err && err.message ? err.message : err), "error");
    },
  });

  const buttons = document.querySelectorAll("paypal-button");
  buttons.forEach((btn) => {
    btn.hidden = false;
    btn.addEventListener("click", async () => {
      showStatus("Starting PayPal checkout...");
      const order = await postJson("/api/orders", { items: typeof readCart === "function" ? readCart() : [] });
      await session.start({ orderId: order.id });
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initPayPalV6().catch((err) => showStatus("PayPal init error: " + err.message, "error"));
});
"""

