# Legacy demo store: Inkwell & Co.

A tiny online shop with a deliberately **outdated** PayPal checkout. CheckoutPilot scans it, finds what's missing, and upgrades it.

## Run it

From the project root (with the venv active):

```
python -m demo_stores.serve legacy
```

Open http://localhost:8101. Add the pen to the cart, go to checkout, and pay with your **Sandbox Personal** account (`sb-...@personal.example.com`), never a real PayPal login.

Payments need `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` (Sandbox) in `.env`, and Member 6's `PayPalClient` to be implemented. Until then, clicking the PayPal button shows "PayPal client is not implemented yet". The pages still load, which is all the scanner needs.

## Deliberate flaws (what CheckoutPilot should find)

| Flaw | Where | Expected issue ID |
|---|---|---|
| PayPal JS SDK v5 (current is v6) | `templates/checkout.html` | `sdk_outdated` |
| No PayPal button on the cart page | `templates/cart.html` | `no_paypal_on_cart` |
| No PayPal button on the product page | `templates/product.html` | `no_paypal_on_product` |
| PayPal button below a long form on mobile | `templates/checkout.html` + `static/style.css` | `button_below_fold_mobile` |

Do **not** fix these by hand. They are the test.

## Layout

```
legacy_store/
  app.py              FastAPI app: pages + /api/orders + /health
  templates/          product.html, cart.html, checkout.html, success.html
  static/             style.css, cart.js (cart in localStorage), checkout.js (SDK v5 buttons)
```

The code agent copies this whole folder and patches the copy, so keep everything the store needs inside it.

## Contract (don't rename)

- Pages: `/`, `/cart`, `/checkout`, `/success`
- Element IDs: `#add-to-cart`, `#go-to-cart`, `#go-to-checkout`, `#paypal-button-container`, `#order-status`
- API: `GET /api/products`, `POST /api/orders` with `{"items": [{"id": "brass-pen", "qty": 1}]}`, `POST /api/orders/{id}/capture`, `GET /health`
- Prices are calculated on the server. The browser only sends item IDs and quantities.
