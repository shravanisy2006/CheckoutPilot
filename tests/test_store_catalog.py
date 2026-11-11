"""Inkwell & Co. looks like a real shop: catalogue, categories, product pages. Run: pytest tests/test_store_catalog.py -v"""

import importlib.util
import json
from decimal import Decimal
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

STORES = Path("demo_stores")


def _client(store: str) -> TestClient:
    spec = importlib.util.spec_from_file_location(f"{store}_catalog_app", STORES / store / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return TestClient(module.app)


@pytest.fixture(params=["legacy_store", "upgraded_store"])
def client(request):
    return _client(request.param)


def test_both_stores_sell_the_same_catalogue():
    legacy = json.loads((STORES / "legacy_store" / "catalog.json").read_text(encoding="utf-8"))
    upgraded = json.loads((STORES / "upgraded_store" / "catalog.json").read_text(encoding="utf-8"))
    assert legacy == upgraded
    assert len(legacy["products"]) >= 12 and len(legacy["categories"]) >= 4
    assert {p["category"] for p in legacy["products"]} <= {c["id"] for c in legacy["categories"]}


def test_shop_lists_every_product(client):
    page = client.get("/shop").text
    for product in client.get("/api/products").json()["products"]:
        assert f'href="/product/{product["id"]}"' in page


def test_category_filter(client):
    page = client.get("/shop?category=inks").text
    assert "Midnight Blue Ink" in page and "Brass Fountain Pen" not in page
    assert client.get("/shop?category=nope").status_code == 404


def test_product_page(client):
    page = client.get("/product/walnut-pen").text
    assert "Walnut Wood Fountain Pen" in page and "$42.00" in page
    assert 'id="add-to-cart"' in page and 'data-id="walnut-pen"' in page
    assert client.get("/product/nope").status_code == 404


def test_every_page_has_the_menu_and_no_unfilled_placeholders(client):
    for path in ["/", "/shop", "/product/ink-blue", "/cart", "/checkout", "/success"]:
        page = client.get(path).text
        assert 'class="site-nav"' in page and 'href="/shop"' in page, path
        assert re.findall(r"\{\{[A-Z_]+\}\}", page) == [], path


def test_home_is_still_the_pen_page_with_more_products(client):
    """The scanner, verifier and code agent start at / and click #add-to-cart: keep it so."""
    page = client.get("/").text
    assert 'id="add-to-cart"' in page and "Machined Brass Fountain Pen" in page
    assert "More from" in page and page.count('class="product-card"') == 4


@pytest.mark.parametrize("store", ["legacy_store", "upgraded_store"])
def test_new_products_are_priced_on_the_server(store):
    """Totals come from the catalogue on the server: 2 x 42.00 + 1 x 6.00 = 90.00."""
    spec = importlib.util.spec_from_file_location(f"{store}_price_app", STORES / store / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    items = [module.CartItem(id="walnut-pen", qty=2), module.CartItem(id="converter", qty=1)]
    assert Decimal(module.calculate_total(items)) == Decimal("90.00")
