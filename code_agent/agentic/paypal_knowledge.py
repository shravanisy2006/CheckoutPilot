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
- **Payment Lifecycle**:
  ```javascript
  // 1. Fetch short-lived client token from merchant's server
  const resp = await fetch('/api/paypal/client-token');
  const { accessToken } = await resp.json();

  // 2. Initialize instance
  const instance = await window.paypal.createInstance({
    clientToken: accessToken,
    components: ['buttons']
  });

  // 3. Create One-Time Payment Session
  const session = await instance.createPayPalOneTimePaymentSession({
    onApprove: async (data) => {
      // Capture order on backend server: POST /api/orders/{id}/capture
      await postJson(`/api/orders/${encodeURIComponent(data.orderID)}/capture`);
      window.location.href = '/success';
    },
    onCancel: () => console.log('Payment cancelled'),
    onError: (err) => console.error('Payment error', err)
  });

  // 4. Bind to <paypal-button> click
  button.addEventListener('click', async () => {
    const order = await postJson('/api/orders', { items: cart });
    await session.start({ orderId: order.id });
  });
  ```

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
