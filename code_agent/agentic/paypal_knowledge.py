"""
Authoritative PayPal JS SDK v6 Migration Handbook.
Injected into the LLM context to guide code generation across any language/framework.
"""

PAYPAL_V6_KNOWLEDGE_BASE = """
# OFFICIAL PAYPAL JAVASCRIPT SDK V6 MIGRATION GUIDE

## 1. Core Differences: v5 vs. v6
- **SDK URL**:
  - Legacy v5: `<script src="https://www.paypal.com/sdk/js?client-id=..."></script>`
  - Modern v6: `<script src="https://www.sandbox.paypal.com/web-sdk/v6/core"></script>` (Sandbox)
               `<script src="https://www.paypal.com/web-sdk/v6/core"></script>` (Production)
- **Token Authorization (Zero-Trust Security)**:
  - In v6, the browser client does NOT trust raw static client IDs alone.
  - The merchant's backend server must provide a short-lived client token endpoint: `GET /api/paypal/client-token` returning `{"accessToken": "<token>"}`.
- **Button Presentment**:
  - Legacy v5: `paypal.Buttons({...}).render('#container-id')`
  - Modern v6: Custom Web Component `<paypal-button id="paypal-button" type="pay"></paypal-button>` inside a container.
- **Loading** (v6 must load async and start from the tag's onload):
  `<script async src="https://www.sandbox.paypal.com/web-sdk/v6/core" onload="onPayPalWebSdkLoaded()" onerror="onPayPalWebSdkFailed()"></script>`
  placed AFTER the page's own scripts (they define onPayPalWebSdkLoaded).
- **Payment Lifecycle** (source: developer.paypal.com/v5-v6):
  ```javascript
  // 1. Short-lived client token from the merchant's server (fallback: the public client ID)
  const { accessToken } = await (await fetch('/api/paypal/client-token')).json();

  // 2. Initialise. The component name is "paypal-payments" ("buttons" is v5 and is REJECTED by v6:
  //    "unrecognized component in createInstance: buttons").
  const sdk = await window.paypal.createInstance({
    clientToken: accessToken,
    components: ['paypal-payments'],
    pageType: 'checkout',
  });

  // 3. Eligibility is explicit in v6
  const methods = await sdk.findEligibleMethods({ currencyCode: 'USD' });
  if (!methods.isEligible('paypal')) return;

  // 4. One-time payment session (note: data.orderId, lower-case "d")
  const session = sdk.createPayPalOneTimePaymentSession({
    onApprove: async (data) => {
      await postJson(`/api/orders/${encodeURIComponent(data.orderId)}/capture`);
      window.location.href = '/success';
    },
    onCancel: () => {},
    onError: (err) => console.error('Payment error', err),
  });

  // 5. Show the hidden <paypal-button> and start the session on click.
  //    The second argument is a PROMISE of {orderId}: call createOrder(), don't pass the function.
  const button = document.querySelector('#paypal-button-container paypal-button');
  button.removeAttribute('hidden');
  button.addEventListener('click', () => session.start({ presentationMode: 'auto' }, createOrder()));
  // where: async function createOrder() { const o = await postJson('/api/orders', {items}); return { orderId: o.id }; }
  ```
- **Keep the page's other jobs**: if the v5 script also drew the cart lines or total, the upgrade must keep
  doing that (otherwise the order summary shows $0.00).

## 2. Express Checkout on Cart Page
- For higher conversion, an express `<paypal-button>` must be added directly to the cart page/template so buyers can skip long shipping forms.

## 3. Mobile Viewport Layout Optimization
- On mobile screens (<=760px), checkout buttons must not be hidden below long shipping or billing forms.
- Reorder visual layout (e.g. using CSS grid-template-areas or flexbox) so the payment container appears above the fold.

## 4. STRICT NON-DESTRUCTIVE RULES
- NEVER delete or alter the merchant's product catalogue, pricing calculations, inventory logic, or shipping inputs.
- PRESERVE all existing HTML element IDs and form attributes so other scripts do not break.
- Adapt cleanly to the merchant's framework (FastAPI, Flask, Django, Express, Next.js, PHP, Vanilla HTML).
"""
