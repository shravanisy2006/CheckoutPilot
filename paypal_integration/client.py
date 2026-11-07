"""
PayPal Sandbox client.

Every PayPal REST call lives here, so other modules never deal with tokens or URLs.

    from paypal_integration import PayPalClient
    client = PayPalClient()
    order = client.create_order("35.00")            # {"id", "status", "approve_url"}
    ...buyer approves in the PayPal popup...
    result = client.capture_order(order["id"])      # {"id", "status", "capture_id", ...}

APIs used (Sandbox only):
  - OAuth token:  POST /v1/oauth2/token
  - Orders v2:    POST /v2/checkout/orders, GET /v2/checkout/orders/{id},
                  POST /v2/checkout/orders/{id}/capture

Safety: this client refuses to talk to the Live API (real money). It only
accepts a base URL containing "sandbox".

Failures raise ModuleError with one of the codes in paypal_integration/errors.py.
"""

import os
import time
import uuid
from decimal import Decimal, InvalidOperation

import requests
from dotenv import load_dotenv

from paypal_integration.errors import (
    PAYPAL_AUTH_FAILED,
    PAYPAL_LIVE_BLOCKED,
    PAYPAL_NOT_CONFIGURED,
    PAYPAL_REQUEST_FAILED,
    PAYPAL_UNAVAILABLE,
    ModuleError,
)

load_dotenv()

DEFAULT_API_BASE = "https://api-m.sandbox.paypal.com"
REQUEST_TIMEOUT_SECONDS = 30
TOKEN_SAFETY_MARGIN_SECONDS = 60  # refresh the token a minute before it expires


def _clean_amount(amount) -> str:
    """Turn 35, "35", Decimal("35.0") into "35.00". Reject zero, negatives and junk."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise ModuleError(PAYPAL_REQUEST_FAILED, f"Invalid amount: {amount!r}") from None
    if not value.is_finite() or value <= 0:
        raise ModuleError(PAYPAL_REQUEST_FAILED, f"Amount must be more than zero, got {amount!r}")
    return f"{value.quantize(Decimal('0.01'))}"


def _paypal_error_text(response: requests.Response) -> str:
    """Short, readable reason from a PayPal error response."""
    try:
        data = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    name = data.get("name") or data.get("error") or f"HTTP {response.status_code}"
    details = data.get("details") or []
    issue = details[0].get("issue") if details and isinstance(details[0], dict) else ""
    message = data.get("message") or data.get("error_description") or ""
    return " - ".join(part for part in (name, issue, message) if part)


class PayPalClient:
    """Small wrapper around the PayPal Sandbox REST APIs."""

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 api_base: str | None = None, session: requests.Session | None = None) -> None:
        self.client_id = (client_id if client_id is not None else os.getenv("PAYPAL_CLIENT_ID", "")).strip()
        self.client_secret = (client_secret if client_secret is not None
                              else os.getenv("PAYPAL_CLIENT_SECRET", "")).strip()
        self.api_base = (api_base or os.getenv("PAYPAL_API_BASE", "") or DEFAULT_API_BASE).strip().rstrip("/")
        self.session = session or requests.Session()
        self._token = ""
        self._token_expires_at = 0.0

    # ------------------------------------------------------------ setup ---
    def is_configured(self) -> bool:
        """True if sandbox credentials are present in .env."""
        placeholders = {"", "your-sandbox-client-id-here", "your-sandbox-client-secret-here"}
        return self.client_id not in placeholders and self.client_secret not in placeholders

    def _check_ready(self) -> None:
        if "sandbox" not in self.api_base:
            raise ModuleError(PAYPAL_LIVE_BLOCKED,
                              f"Refusing to use {self.api_base}. CheckoutPilot only uses the PayPal Sandbox.")
        if not self.is_configured():
            raise ModuleError(PAYPAL_NOT_CONFIGURED,
                              "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (Sandbox) in .env.")

    # ------------------------------------------------------------- HTTP ---
    def _send(self, method: str, path: str, **kwargs) -> requests.Response:
        try:
            return self.session.request(method, f"{self.api_base}{path}",
                                        timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
        except requests.RequestException as error:
            raise ModuleError(PAYPAL_UNAVAILABLE, f"Could not reach PayPal: {error}") from error

    def get_access_token(self) -> str:
        """Get (and cache) an OAuth access token using the client ID and secret."""
        self._check_ready()
        if self._token and time.time() < self._token_expires_at:
            return self._token
        response = self._send(
            "POST", "/v1/oauth2/token",
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
        if response.status_code in (401, 403):
            raise ModuleError(PAYPAL_AUTH_FAILED,
                              "PayPal rejected the client ID / secret. Check the Sandbox app credentials in .env.")
        if response.status_code >= 400:
            code = PAYPAL_UNAVAILABLE if response.status_code >= 500 else PAYPAL_AUTH_FAILED
            raise ModuleError(code, f"Token request failed: {_paypal_error_text(response)}")
        data = response.json()
        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 300))
        self._token_expires_at = time.time() + max(expires_in - TOKEN_SAFETY_MARGIN_SECONDS, 30)
        return self._token

    def _api(self, method: str, path: str, body: dict | None = None, idempotent: bool = False) -> dict:
        """Call a REST API with the bearer token. Retries once if the token expired."""
        request_id = str(uuid.uuid4())  # same ID on retry, so PayPal never creates/captures twice
        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {self.get_access_token()}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            }
            if idempotent:
                headers["PayPal-Request-Id"] = request_id
            response = self._send(method, path, json=body, headers=headers)
            if response.status_code == 401 and attempt == 0:
                self._token = ""  # token expired: get a new one and try again
                continue
            break
        if response.status_code >= 500:
            raise ModuleError(PAYPAL_UNAVAILABLE, f"PayPal error: {_paypal_error_text(response)}")
        if response.status_code == 401:
            raise ModuleError(PAYPAL_AUTH_FAILED, f"PayPal rejected the token: {_paypal_error_text(response)}")
        if response.status_code >= 400:
            raise ModuleError(PAYPAL_REQUEST_FAILED, _paypal_error_text(response))
        return response.json() if response.content else {}

    # ----------------------------------------------------------- Orders ---
    def create_order(self, amount, currency: str = "USD") -> dict:
        """Create a Sandbox order. Returns {"id", "status", "approve_url"}."""
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{"amount": {"currency_code": currency, "value": _clean_amount(amount)}}],
        }
        data = self._api("POST", "/v2/checkout/orders", body, idempotent=True)
        approve_url = next((link["href"] for link in data.get("links", [])
                            if link.get("rel") in ("approve", "payer-action")), "")
        return {"id": data.get("id", ""), "status": data.get("status", ""), "approve_url": approve_url}

    def get_order(self, order_id: str) -> dict:
        """Fetch an order. Returns {"id", "status", "amount", "currency"}."""
        data = self._api("GET", f"/v2/checkout/orders/{_safe_id(order_id)}")
        amount = (data.get("purchase_units") or [{}])[0].get("amount", {})
        return {"id": data.get("id", ""), "status": data.get("status", ""),
                "amount": amount.get("value", ""), "currency": amount.get("currency_code", "")}

    def capture_order(self, order_id: str) -> dict:
        """Capture an approved order.

        Returns {"id", "status", "capture_id", "capture_status", "amount", "currency", "payer_email"}.
        status is "COMPLETED" when the money moved.
        """
        data = self._api("POST", f"/v2/checkout/orders/{_safe_id(order_id)}/capture", {}, idempotent=True)
        units = data.get("purchase_units") or [{}]
        captures = (units[0].get("payments") or {}).get("captures") or [{}]
        capture = captures[0]
        amount = capture.get("amount", {})
        return {
            "id": data.get("id", ""),
            "status": data.get("status", ""),
            "capture_id": capture.get("id", ""),
            "capture_status": capture.get("status", ""),
            "amount": amount.get("value", ""),
            "currency": amount.get("currency_code", ""),
            "payer_email": (data.get("payer") or {}).get("email_address", ""),
        }


def _safe_id(order_id: str) -> str:
    """PayPal order IDs are letters and digits. Reject anything else (no path tricks)."""
    order_id = str(order_id).strip()
    if not order_id or not order_id.isalnum() or len(order_id) > 64:
        raise ModuleError(PAYPAL_REQUEST_FAILED, f"Invalid PayPal order ID: {order_id!r}")
    return order_id
