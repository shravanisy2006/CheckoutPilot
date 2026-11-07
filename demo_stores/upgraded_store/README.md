# Upgraded demo store: Inkwell & Co. (after CheckoutPilot)

The same shop as `legacy_store`, with the PayPal upgrades CheckoutPilot recommends. It's the "after" picture in the demo.

## Run it

From the project root (venv active):

```
python -m demo_stores.serve upgraded
```

Open http://localhost:8102 and pay with your **United States Sandbox Personal** account.

## What changed compared with legacy_store

| Legacy flaw | Upgrade here | Files |
|---|---|---|
| PayPal JS SDK v5 (`paypal.com/sdk/js`) | SDK v6 (`web-sdk/v6/core`), `createInstance` + one-time payment session + `<paypal-button>` | `static/paypal.js`, `templates/cart.html`, `templates/checkout.html` |
| No PayPal on the cart page | PayPal express button on the cart | `templates/cart.html` |
| PayPal below the fold on mobile | Summary + PayPal come before the form on mobile | `templates/checkout.html`, `static/style.css` |

The product page still has no PayPal button (CheckoutPilot reports it as a medium issue, not auto-fixed).

## How v6 checkout works here

1. The page loads `https://www.sandbox.paypal.com/web-sdk/v6/core`.
2. `paypal.js` asks our server for a browser-safe client token (`GET /api/paypal/client-token`). The secret never reaches the browser.
3. `paypal.createInstance(...)`, then `findEligibleMethods`, then `createPayPalOneTimePaymentSession`.
4. Clicking `<paypal-button>` calls `session.start(..., createOrder())`. The server creates the order at its own price (`POST /api/orders`).
5. `onApprove` captures via `POST /api/orders/{id}/capture` and shows `/success`.

The element IDs and API routes are the same as the legacy store.
