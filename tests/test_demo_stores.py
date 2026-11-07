"""Tests for the legacy demo store and the store launcher. Run with: pytest tests/test_demo_stores.py -v"""

import importlib.util
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo_stores import serve

LEGACY_DIR = Path(__file__).resolve().parent.parent / "demo_stores" / "legacy_store"


def load_store_app():
    spec = importlib.util.spec_from_file_location("legacy_store_app", LEGACY_DIR / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def store():
    return load_store_app()


@pytest.fixture
def client(store):
    return TestClient(store.app)


class FakePayPal:
    created = []

    def create_order(self, amount, currency="USD"):
        FakePayPal.created.append((amount, currency))
        return {"id": "ORDER123", "status": "CREATED"}

    def capture_order(self, order_id):
        return {"id": order_id, "status": "COMPLETED"}


# --------------------------------------------------------------- pages ---
@pytest.mark.parametrize("path", ["/", "/cart", "/checkout", "/success"])
def test_pages_load(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "{{" not in response.text  # every placeholder filled


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "store": "legacy", "paypal_sdk": "v5"}


def test_stable_ids_present(client):
    assert 'id="add-to-cart"' in client.get("/").text
    assert 'id="go-to-cart"' in client.get("/").text
    assert 'id="go-to-checkout"' in client.get("/cart").text
    checkout = client.get("/checkout").text
    assert 'id="paypal-button-container"' in checkout and 'id="order-status"' in checkout


def test_deliberate_flaws(client):
    checkout = client.get("/checkout").text
    assert "https://www.paypal.com/sdk/js?" in checkout  # SDK v5
    assert "web-sdk/v6" not in checkout
    for path in ("/", "/cart"):
        page = client.get(path).text
        assert "paypal-button-container" not in page and "paypal.com/sdk" not in page
    # On mobile the form comes before the PayPal button.
    assert checkout.index('id="shipping-form"') < checkout.index('id="paypal-button-container"')


def test_client_id_from_env_and_fallback(monkeypatch, client):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    assert "client-id=sb&" in client.get("/checkout").text
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "test-sandbox-id")
    assert "client-id=test-sandbox-id&" in client.get("/checkout").text


def test_static_files(client):
    assert client.get("/static/checkout.js").status_code == 200
    assert "paypal.Buttons" in client.get("/static/checkout.js").text
    assert client.get("/static/style.css").status_code == 200


# ----------------------------------------------------------------- API ---
def test_products(client):
    data = client.get("/api/products").json()
    assert data["currency"] == "USD"
    assert {p["id"] for p in data["products"]} == {"brass-pen", "ink-blue"}


def test_create_order_uses_server_prices(store, client, monkeypatch):
    FakePayPal.created = []
    monkeypatch.setattr(store, "_paypal_client", lambda: FakePayPal())
    body = {"items": [{"id": "brass-pen", "qty": 2}, {"id": "ink-blue", "qty": 1}], "total": "0.01"}
    response = client.post("/api/orders", json=body)
    assert response.status_code == 200
    assert response.json() == {"id": "ORDER123", "status": "CREATED", "total": "82.00"}
    assert FakePayPal.created == [("82.00", "USD")]  # browser "total" ignored


def test_capture_order(store, client, monkeypatch):
    monkeypatch.setattr(store, "_paypal_client", lambda: FakePayPal())
    response = client.post("/api/orders/ORDER123/capture")
    assert response.json() == {"id": "ORDER123", "status": "COMPLETED"}


@pytest.mark.parametrize("body", [
    {"items": []},
    {"items": [{"id": "brass-pen", "qty": 0}]},
    {"items": [{"id": "brass-pen", "qty": 11}]},
    {"items": [{"id": "brass-pen", "qty": -1}]},
])
def test_create_order_rejects_bad_quantities(client, body):
    assert client.post("/api/orders", json=body).status_code == 422


def test_create_order_rejects_unknown_product(client):
    response = client.post("/api/orders", json={"items": [{"id": "free-gold", "qty": 1}]})
    assert response.status_code == 400


def test_placeholder_paypal_client_gives_clear_error(store, client, monkeypatch):
    class Placeholder:
        def create_order(self, amount, currency="USD"):
            return {}
    monkeypatch.setattr(store, "_paypal_client", lambda: Placeholder())
    response = client.post("/api/orders", json={"items": [{"id": "brass-pen", "qty": 1}]})
    assert response.status_code == 503
    assert "not implemented" in response.json()["detail"]


def test_paypal_error_becomes_502(store, client, monkeypatch):
    class Broken:
        def create_order(self, amount, currency="USD"):
            error = RuntimeError("boom")
            error.code, error.message = "PAYPAL_AUTH_FAILED", "bad credentials"
            raise error
    monkeypatch.setattr(store, "_paypal_client", lambda: Broken())
    response = client.post("/api/orders", json={"items": [{"id": "brass-pen", "qty": 1}]})
    assert response.status_code == 502
    assert response.json()["detail"] == "PAYPAL_AUTH_FAILED: bad credentials"


# ------------------------------------------------------------ launcher ---
def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_resolve_store_names():
    folder, port = serve.resolve_store("legacy")
    assert folder == LEGACY_DIR and port == 8101


def test_start_store_rejects_folder_without_app(tmp_path):
    with pytest.raises(serve.StoreError):
        serve.start_store(tmp_path, free_port())


def test_start_and_stop_real_store():
    import requests
    port = free_port()
    url = serve.start_store(LEGACY_DIR, port)
    try:
        assert url == f"http://localhost:{port}"
        assert requests.get(f"{url}/health", timeout=5).json()["store"] == "legacy"
        assert "Inkwell" in requests.get(f"{url}/cart", timeout=5).text
    finally:
        assert serve.stop_store(port) is True
    assert serve.stop_store(port) is False


def test_start_store_patched_copy(tmp_path):
    """The code agent will run a patched copy from another folder; that must work too."""
    import shutil
    import requests
    copy = tmp_path / "patched_store"
    shutil.copytree(LEGACY_DIR, copy)
    port = free_port()
    url = serve.start_store(copy, port)
    try:
        assert requests.get(f"{url}/health", timeout=5).status_code == 200
    finally:
        serve.stop_store(port)


def test_cli_needs_port_for_paths(tmp_path):
    with pytest.raises(SystemExit):
        serve.main([str(tmp_path)])
    assert serve.main([str(tmp_path), "--port", "9999"]) == 1  # no app.py
