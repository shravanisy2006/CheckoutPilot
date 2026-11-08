"""PayPal integration: all calls to PayPal's Sandbox REST APIs live here."""

import os

from paypal_integration.client import PayPalClient
from paypal_integration.errors import ModuleError
from paypal_integration.mock import MockPayPalClient


def get_paypal_client():
    """Real Sandbox client, or the fake one when MOCK_PAYPAL=true in .env."""
    if os.getenv("MOCK_PAYPAL", "false").strip().lower() in ("1", "true", "yes"):
        return MockPayPalClient()
    return PayPalClient()


__all__ = ["PayPalClient", "MockPayPalClient", "ModuleError", "get_paypal_client"]
