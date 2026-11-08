"""
Upgraded demo store - "Inkwell & Co." (port 8102).

The same shop as legacy_store, after the PayPal upgrades CheckoutPilot recommends:
  - PayPal JavaScript SDK v6 (web-sdk/v6/core) instead of v5
  - PayPal button on the cart page (express checkout), not only at checkout
  - On mobile, the order summary and PayPal button come BEFORE the long form

Run it (from the project root):
    python -m demo_stores.serve upgraded

Pages:   /  (product)   /cart   /checkout   /success
API:     GET /api/products
         GET /api/paypal/client-token     (browser-safe token for SDK v6)
         POST /api/orders                  body: {"items": [{"id": "...", "qty": 1}]}
         POST /api/orders/{order_id}/capture
         GET /health

Stable element IDs used by the scanner and verifier (do not rename):
  #add-to-cart  #go-to-cart  #go-to-checkout  #paypal-button-container  #order-status

Prices are always calculated on the server from PRODUCTS, never trusted from
the browser. PayPal calls go through paypal_integration.PayPalClient.
"""

import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

STORE_DIR = Path(__file__).resolve().parent
STORE_NAME = "Inkwell & Co."
CURRENCY = "USD"

# The product catalogue. Prices are strings so they stay exact.
PRODUCTS: dict[str, dict] = {
    "brass-pen": {
        "id": "brass-pen",
        "name": "Machined Brass Fountain Pen",
        "price": "35.00",
        "description": "A compact brass fountain pen with a smooth steel nib. Refillable and built to last.",
    },
    "ink-blue": {
        "id": "ink-blue",
        "name": "Midnight Blue Ink, 50 ml",
        "price": "12.00",
        "description": "Water-based ink that dries quickly and stays vivid.",
    },
}

MAX_QTY_PER_ITEM = 10

app = FastAPI(title=f"{STORE_NAME} (upgraded demo store)")

SANDBOX_SDK_URL = "https://www.sandbox.paypal.com/web-sdk/v6/core"
app.mount("/static", StaticFiles(directory=STORE_DIR / "static"), name="static")


# ---------------------------------------------------------------- pages ---
def _paypal_client_id() -> str:
    """Sandbox client ID for the JS SDK. "sb" is PayPal's generic sandbox ID for demos."""
    return os.getenv("PAYPAL_CLIENT_ID", "").strip() or "sb"


def render(template: str) -> HTMLResponse:
    """Return an HTML page from templates/, filling in simple {{PLACEHOLDERS}}."""
    html = (STORE_DIR / "templates" / template).read_text(encoding="utf-8")
    html = html.replace("{{STORE_NAME}}", STORE_NAME)
    html = html.replace("{{PAYPAL_CLIENT_ID}}", _paypal_client_id())
    html = html.replace("{{CURRENCY}}", CURRENCY)
    html = html.replace("{{PAYPAL_SDK_URL}}", SANDBOX_SDK_URL)
    return HTMLResponse(html)


@app.get("/", response_class=HTMLResponse)
def product_page() -> HTMLResponse:
    return render("product.html")


@app.get("/cart", response_class=HTMLResponse)
def cart_page() -> HTMLResponse:
    return render("cart.html")


@app.get("/checkout", response_class=HTMLResponse)
def checkout_page() -> HTMLResponse:
    return render("checkout.html")


@app.get("/success", response_class=HTMLResponse)
def success_page() -> HTMLResponse:
    return render("success.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "store": "upgraded", "paypal_sdk": "v6"}


# ------------------------------------------------------------------ API ---
@app.get("/api/products")
def list_products() -> dict:
    return {"currency": CURRENCY, "products": list(PRODUCTS.values())}


@app.get("/api/paypal/client-token")
def client_token() -> dict:
    """Short-lived, browser-safe token the v6 SDK needs. The secret never leaves the server."""
    client = _paypal_client()
    try:
        token = client.get_client_token()
    except Exception as error:
        code = getattr(error, "code", "PAYPAL_ERROR")
        message = getattr(error, "message", str(error))
        raise HTTPException(status_code=502, detail=f"{code}: {message}") from error
    if not token:
        raise HTTPException(status_code=503, detail="PayPal client returned no client token.")
    return {"accessToken": token}


class CartItem(BaseModel):
    id: str
    qty: int = Field(ge=1, le=MAX_QTY_PER_ITEM)


class CreateOrderRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1)


def calculate_total(items: list[CartItem]) -> str:
    """Total price of the cart, calculated from the server's own catalogue."""
    total = Decimal("0.00")
    for item in items:
        product = PRODUCTS.get(item.id)
        if product is None:
            raise HTTPException(status_code=400, detail=f"Unknown product: {item.id}")
        total += Decimal(product["price"]) * item.qty
    return f"{total:.2f}"


def _paypal_client():
    """Create the shared PayPal client (owned by Member 6, paypal_integration/)."""
    try:
        from paypal_integration import PayPalClient
    except ImportError as error:  # store started outside the project
        raise HTTPException(status_code=503, detail="PayPal client not available.") from error
    return PayPalClient()


def _call_paypal(action, *args) -> dict:
    """Run a PayPal client call and turn failures into clean HTTP errors."""
    try:
        result = action(*args)
    except HTTPException:
        raise
    except Exception as error:  # PayPal errors (ModuleError or others) -> 502
        code = getattr(error, "code", "PAYPAL_ERROR")
        message = getattr(error, "message", str(error))
        raise HTTPException(status_code=502, detail=f"{code}: {message}") from error
    if not result or not result.get("id"):
        raise HTTPException(status_code=503, detail="PayPal client is not implemented yet (returned no order).")
    return result


@app.post("/api/orders")
def create_order(request: CreateOrderRequest) -> dict:
    """Create a PayPal order for the cart. Returns {"id": "<PayPal order ID>", "total": "..."}."""
    total = calculate_total(request.items)
    client = _paypal_client()
    order = _call_paypal(client.create_order, total, CURRENCY)
    return {"id": order["id"], "status": order.get("status", ""), "total": total}


@app.post("/api/orders/{order_id}/capture")
def capture_order(order_id: str) -> dict:
    """Capture an approved PayPal order. Returns {"id", "status"}."""
    client = _paypal_client()
    result = _call_paypal(client.capture_order, order_id)
    return {"id": result["id"], "status": result.get("status", "")}
