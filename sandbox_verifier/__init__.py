"""Sandbox verifier: proves a checkout works by completing a PayPal Sandbox test purchase."""

import os

from sandbox_verifier.mock import verify_checkout_mock
from sandbox_verifier.verifier import compare_runs, verify_checkout


def get_verifier():
    """Real verifier, or the fake one when MOCK_VERIFIER=true in .env."""
    if os.getenv("MOCK_VERIFIER", "false").strip().lower() in ("1", "true", "yes"):
        return verify_checkout_mock
    return verify_checkout


__all__ = ["verify_checkout", "verify_checkout_mock", "compare_runs", "get_verifier"]
