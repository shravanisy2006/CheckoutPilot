"""Tests for the PayPal Sandbox client (no real network calls). Run: pytest tests/test_paypal_client.py -v"""

import pytest
import requests

from paypal_integration import MockPayPalClient, PayPalClient, get_paypal_client
from paypal_integration import client as client_module
from paypal_integration.errors import ModuleError
from paypal_integration.try_paypal import main as try_main

BASE = "https://api-m.sandbox.paypal.com"


class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data if data is not None else {}
        self.content = b"x" if data is not None else b""

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


class FakeSession:
    """Plays back queued responses and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


TOKEN = FakeResponse(200, {"access_token": "tok-1", "expires_in": 32400})


def make_client(*responses):
    session = FakeSession(*responses)
    return PayPalClient("id-123", "secret-456", BASE, session=session), session


ORDER_CREATED = FakeResponse(201, {
    "id": "5O190127TN364715T", "status": "CREATED",
    "links": [{"rel": "self", "href": "x"}, {"rel": "approve", "href": "https://sandbox.paypal.com/approve?t=1"}],
})
ORDER_CAPTURED = FakeResponse(201, {
    "id": "5O190127TN364715T", "status": "COMPLETED",
    "payer": {"email_address": "sb-buyer@personal.example.com"},
    "purchase_units": [{"payments": {"captures": [
        {"id": "3C679366HH908993F", "status": "COMPLETED", "amount": {"value": "35.00", "currency_code": "USD"}},
    ]}}],
})


# ------------------------------------------------------------- happy path ---
def test_create_order():
    client, session = make_client(TOKEN, ORDER_CREATED)
    order = client.create_order(35)
    assert order == {"id": "5O190127TN364715T", "status": "CREATED",
                     "approve_url": "https://sandbox.paypal.com/approve?t=1"}
    token_call, order_call = session.calls
    assert token_call["url"] == f"{BASE}/v1/oauth2/token"
    assert token_call["auth"] == ("id-123", "secret-456")
    assert order_call["url"] == f"{BASE}/v2/checkout/orders"
    assert order_call["headers"]["Authorization"] == "Bearer tok-1"
    assert order_call["headers"]["PayPal-Request-Id"]
    assert order_call["json"]["intent"] == "CAPTURE"
    assert order_call["json"]["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "35.00"}


def test_capture_order():
    client, session = make_client(TOKEN, ORDER_CAPTURED)
    result = client.capture_order("5O190127TN364715T")
    assert result == {"id": "5O190127TN364715T", "status": "COMPLETED", "capture_id": "3C679366HH908993F",
                      "capture_status": "COMPLETED", "amount": "35.00", "currency": "USD",
                      "payer_email": "sb-buyer@personal.example.com"}
    assert session.calls[1]["url"].endswith("/v2/checkout/orders/5O190127TN364715T/capture")


def test_get_order():
    data = {"id": "ABC123", "status": "APPROVED",
            "purchase_units": [{"amount": {"value": "12.00", "currency_code": "USD"}}]}
    client, _ = make_client(TOKEN, FakeResponse(200, data))
    assert client.get_order("ABC123") == {"id": "ABC123", "status": "APPROVED", "amount": "12.00", "currency": "USD"}


def test_token_is_cached():
    client, session = make_client(TOKEN, ORDER_CREATED, ORDER_CREATED)
    client.create_order("1.00")
    client.create_order("1.00")
    assert [c["url"].endswith("/oauth2/token") for c in session.calls] == [True, False, False]


def test_expired_token_is_refreshed_once():
    token2 = FakeResponse(200, {"access_token": "tok-2", "expires_in": 32400})
    client, session = make_client(TOKEN, FakeResponse(401, {"name": "AUTHENTICATION_FAILURE"}), token2, ORDER_CREATED)
    assert client.create_order("1.00")["id"] == "5O190127TN364715T"
    first, retry = session.calls[1], session.calls[3]
    assert retry["headers"]["Authorization"] == "Bearer tok-2"
    assert first["headers"]["PayPal-Request-Id"] == retry["headers"]["PayPal-Request-Id"]


# ---------------------------------------------------------------- safety ---
def test_refuses_live_api():
    client = PayPalClient("id", "secret", "https://api-m.paypal.com", session=FakeSession())
    with pytest.raises(ModuleError) as error:
        client.create_order("1.00")
    assert error.value.code == "PAYPAL_LIVE_BLOCKED"


@pytest.mark.parametrize("client_id, secret", [("", "s"), ("id", ""), ("your-sandbox-client-id-here", "s")])
def test_not_configured(client_id, secret):
    client = PayPalClient(client_id, secret, BASE, session=FakeSession())
    assert client.is_configured() is False
    with pytest.raises(ModuleError) as error:
        client.get_access_token()
    assert error.value.code == "PAYPAL_NOT_CONFIGURED"


@pytest.mark.parametrize("amount", ["0", "-5", "abc", "NaN", None])
def test_bad_amounts(amount):
    client, _ = make_client(TOKEN)
    with pytest.raises(ModuleError) as error:
        client.create_order(amount)
    assert error.value.code == "PAYPAL_REQUEST_FAILED"


@pytest.mark.parametrize("order_id", ["", "../v1/oauth2/token", "abc/def", "A" * 65])
def test_bad_order_ids(order_id):
    client, session = make_client()
    with pytest.raises(ModuleError):
        client.capture_order(order_id)
    assert session.calls == []


# ---------------------------------------------------------------- errors ---
def test_wrong_credentials():
    client, _ = make_client(FakeResponse(401, {"error": "invalid_client", "error_description": "Client Authentication failed"}))
    with pytest.raises(ModuleError) as error:
        client.get_access_token()
    assert error.value.code == "PAYPAL_AUTH_FAILED"


def test_network_down():
    client, _ = make_client(requests.ConnectionError("no internet"))
    with pytest.raises(ModuleError) as error:
        client.get_access_token()
    assert error.value.code == "PAYPAL_UNAVAILABLE"


def test_paypal_server_error():
    client, _ = make_client(TOKEN, FakeResponse(503, {"name": "SERVICE_UNAVAILABLE"}))
    with pytest.raises(ModuleError) as error:
        client.create_order("1.00")
    assert error.value.code == "PAYPAL_UNAVAILABLE"


def test_unapproved_capture_gives_readable_error():
    body = {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_NOT_APPROVED"}],
            "message": "The requested action could not be performed."}
    client, _ = make_client(TOKEN, FakeResponse(422, body))
    with pytest.raises(ModuleError) as error:
        client.capture_order("ABC123")
    assert error.value.code == "PAYPAL_REQUEST_FAILED"
    assert "ORDER_NOT_APPROVED" in error.value.message


def test_secret_never_in_error_messages():
    client, _ = make_client(FakeResponse(401, {"error": "invalid_client"}))
    with pytest.raises(ModuleError) as error:
        client.get_access_token()
    assert "secret-456" not in str(error.value)


# ------------------------------------------------------------- mock + CLI ---
def test_mock_client_full_flow():
    mock = MockPayPalClient()
    order = mock.create_order("35")
    assert mock.get_order(order["id"])["amount"] == "35.00"
    assert mock.capture_order(order["id"])["status"] == "COMPLETED"
    with pytest.raises(ModuleError):
        mock.capture_order(order["id"])  # can't capture twice


def test_get_paypal_client_switch(monkeypatch):
    monkeypatch.setenv("MOCK_PAYPAL", "true")
    assert isinstance(get_paypal_client(), MockPayPalClient)
    monkeypatch.setenv("MOCK_PAYPAL", "false")
    assert isinstance(get_paypal_client(), PayPalClient)


def test_try_paypal_reports_missing_credentials(monkeypatch, capsys):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "")
    assert try_main([]) == 2
    assert "PAYPAL_NOT_CONFIGURED" in capsys.readouterr().out


def test_try_paypal_creates_order(monkeypatch, capsys):
    session = FakeSession(TOKEN, ORDER_CREATED)
    real_init = client_module.PayPalClient.__init__
    monkeypatch.setattr(client_module.PayPalClient, "__init__",
                        lambda self: real_init(self, "id", "secret", BASE, session=session))
    assert try_main([]) == 0
    out = capsys.readouterr().out
    assert "5O190127TN364715T" in out and "tok-1" not in out
