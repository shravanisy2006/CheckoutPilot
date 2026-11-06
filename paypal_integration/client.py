"""
PayPal Sandbox client.

Keep every PayPal API call in this one place so other modules never deal
with tokens or URLs directly.

APIs we expect to use (Sandbox only):
  - OAuth token:            POST /v1/oauth2/token
  - Orders v2:              create / get / capture orders
  - Payment Method Tokens:  saved (vaulted) PayPal accounts
  - Webhooks:               capture and vault events

STATUS: placeholder only. No real API calls yet.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class PayPalClient:
    """Small wrapper around the PayPal Sandbox REST APIs."""

    def __init__(self) -> None:
        self.client_id = os.getenv("PAYPAL_CLIENT_ID", "")
        self.client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
        self.api_base = os.getenv("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")

    def is_configured(self) -> bool:
        """Return True if sandbox credentials are present in .env."""
        return bool(self.client_id and self.client_secret)

    def get_access_token(self) -> str:
        """
        Get an OAuth access token.

        TODO: POST to {api_base}/v1/oauth2/token with client_id/secret (Basic auth).
        """
        return ""

    def create_order(self, amount: str, currency: str = "USD") -> dict:
        """
        Create a sandbox order.

        TODO: POST to {api_base}/v2/checkout/orders.
        """
        return {}

    def get_order(self, order_id: str) -> dict:
        """
        Fetch order details (used to confirm a capture happened).

        TODO: GET {api_base}/v2/checkout/orders/{order_id}.
        """
        return {}

    def capture_order(self, order_id: str) -> dict:
        """
        Capture payment for an approved order.

        TODO: POST to {api_base}/v2/checkout/orders/{order_id}/capture.
        """
        return {}
