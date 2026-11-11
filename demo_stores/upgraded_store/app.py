"""
Upgraded demo store - "Inkwell & Co." (port 8102).

The same shop as legacy_store, after the PayPal upgrades CheckoutPilot recommends:
  - PayPal JavaScript SDK v6 (web-sdk/v6/core) instead of v5
  - PayPal button on the cart page (express checkout), not only at checkout
  - On mobile, the order summary and PayPal button come BEFORE the long form

Run it (from the project root):
    python -m demo_stores.serve upgraded

Pages:   /  (featured product)   /shop   /product/<id>   /cart   /checkout   /success
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

import html as html_lib
import json
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

# The product catalogue lives in catalog.json. Prices are strings so they stay exact.
CATALOG = json.loads((STORE_DIR / "catalog.json").read_text(encoding="utf-8"))
CATEGORIES: dict[str, str] = {c["id"]: c["name"] for c in CATALOG["categories"]}
PRODUCTS: dict[str, dict] = {p["id"]: p for p in CATALOG["products"]}

MAX_QTY_PER_ITEM = 10

app = FastAPI(title=f"{STORE_NAME} (upgraded demo store)")

SANDBOX_SDK_URL = "https://www.sandbox.paypal.com/web-sdk/v6/core"
app.mount("/static", StaticFiles(directory=STORE_DIR / "static"), name="static")


# ---------------------------------------------------------------- pages ---
def _paypal_client_id() -> str:
    """Sandbox client ID for the JS SDK. "sb" is PayPal's generic sandbox ID for demos."""
    return os.getenv("PAYPAL_CLIENT_ID", "").strip() or "sb"


def render(template: str, values: dict[str, str] | None = None, active: str = "") -> HTMLResponse:
    """Return an HTML page from templates/, filling in simple {{PLACEHOLDERS}}.

    ``values`` fills page-specific placeholders (already HTML-escaped by the caller);
    ``active`` highlights a link in the store menu.
    """
    html = (STORE_DIR / "templates" / template).read_text(encoding="utf-8")
    html = html.replace("{{STORE_NAME}}", STORE_NAME)
    html = html.replace("{{PAYPAL_CLIENT_ID}}", _paypal_client_id())
    html = html.replace("{{CURRENCY}}", CURRENCY)
    html = html.replace("{{PAYPAL_SDK_URL}}", SANDBOX_SDK_URL)
    html = html.replace("{{SITE_NAV}}", _site_nav(active))
    for key, value in (values or {}).items():
        html = html.replace("{{" + key + "}}", value)
    return HTMLResponse(html)


@app.get("/", response_class=HTMLResponse)
def product_page() -> HTMLResponse:
    more = [PRODUCTS[pid] for pid in FEATURED if pid in PRODUCTS]
    return render("product.html", {"MORE_PRODUCTS": "".join(_product_card(p) for p in more)}, active="pens")


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


# ----------------------------------------------------------- shop pages ---
# The catalogue pages (/shop, /product/<id>) are built here from catalog.json.
# They never show PayPal, so they look the same in the legacy and upgraded store.
FEATURED = ["walnut-pen", "ink-blue", "linen-notebook", "pen-case"]


def _esc(text: str) -> str:
    return html_lib.escape(str(text), quote=True)


def _product_svg(product: dict, size: int = 160) -> str:
    """A simple drawing per category, in the product's colour (no image files needed)."""
    c = _esc(product.get("color", "#6b7280"))
    shapes = {
        "pens": f'<rect x="72" y="14" width="16" height="104" rx="7" fill="{c}"/>'
                f'<path d="M72 118 L80 146 L88 118 Z" fill="#6b7280"/><rect x="72" y="40" width="16" height="6" fill="#00000033"/>',
        "inks": f'<rect x="50" y="34" width="60" height="18" rx="4" fill="#30343f"/>'
                f'<rect x="38" y="52" width="84" height="88" rx="14" fill="{c}"/><rect x="52" y="78" width="56" height="34" rx="4" fill="#ffffffcc"/>',
        "notebooks": f'<rect x="34" y="20" width="92" height="120" rx="6" fill="{c}"/>'
                     f'<rect x="112" y="20" width="6" height="120" fill="#00000033"/><rect x="50" y="44" width="48" height="10" rx="2" fill="#ffffff99"/>',
        "paper": f'<rect x="40" y="34" width="84" height="104" rx="2" fill="#d6cdb8"/>'
                 f'<rect x="34" y="26" width="84" height="104" rx="2" fill="{c}" stroke="#c9bfa8"/>',
        "accessories": f'<rect x="28" y="56" width="104" height="48" rx="24" fill="{c}"/>'
                       f'<circle cx="80" cy="80" r="8" fill="#ffffff66"/>',
    }
    shape = shapes.get(product.get("category", ""), shapes["accessories"])
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 160 160" role="img" '
            f'aria-label="{_esc(product["name"])}">{shape}</svg>')


def _product_card(product: dict) -> str:
    badge = f'<span class="badge">{_esc(product["badge"])}</span>' if product.get("badge") else ""
    return (
        f'<article class="product-card">'
        f'<a class="product-card-image" href="/product/{_esc(product["id"])}">{_product_svg(product, 120)}</a>'
        f'{badge}'
        f'<h3><a href="/product/{_esc(product["id"])}">{_esc(product["name"])}</a></h3>'
        f'<p class="price">${_esc(product["price"])}</p>'
        f'<button class="button small quick-add" type="button" data-id="{_esc(product["id"])}">Add to cart</button>'
        f'</article>'
    )


def _site_nav(active: str = "") -> str:
    links = [("shop", "/shop", "Shop all")] + [(cid, f"/shop?category={cid}", name) for cid, name in CATEGORIES.items()]
    return "".join(
        f'<a href="{href}"{" class=\"active\"" if key == active else ""}>{_esc(label)}</a>'
        for key, href, label in links
    )


@app.get("/shop", response_class=HTMLResponse)
def shop_page(category: str = "") -> HTMLResponse:
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=404, detail="Unknown category")
    items = [p for p in PRODUCTS.values() if not category or p["category"] == category]
    title = CATEGORIES.get(category, "All products")
    return render("shop.html", {
        "PAGE_TITLE": _esc(title),
        "PRODUCT_COUNT": str(len(items)),
        "PRODUCT_GRID": "".join(_product_card(p) for p in items),
    }, active=category or "shop")


@app.get("/product/{product_id}", response_class=HTMLResponse)
def item_page(product_id: str) -> HTMLResponse:
    product = PRODUCTS.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Unknown product")
    related = [p for p in PRODUCTS.values() if p["category"] == product["category"] and p["id"] != product_id][:4]
    return render("item.html", {
        "PRODUCT_ID": _esc(product["id"]),
        "PRODUCT_NAME": _esc(product["name"]),
        "PRODUCT_PRICE": _esc(product["price"]),
        "PRODUCT_DESCRIPTION": _esc(product["description"]),
        "PRODUCT_IMAGE": _product_svg(product, 220),
        "CATEGORY_ID": _esc(product["category"]),
        "CATEGORY_NAME": _esc(CATEGORIES.get(product["category"], "")),
        "RELATED_GRID": "".join(_product_card(p) for p in related),
    }, active=product["category"])


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
