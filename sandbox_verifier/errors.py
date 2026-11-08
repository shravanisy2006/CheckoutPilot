"""Errors raised by the sandbox verifier for setup problems."""

try:
    from backend.schemas.models import ModuleError  # type: ignore
except ImportError:  # pragma: no cover
    from paypal_integration.errors import ModuleError

VERIFY_NOT_CONFIGURED = "VERIFY_NOT_CONFIGURED"    # buyer email/password missing in .env
VERIFY_BAD_STORE_URL = "VERIFY_BAD_STORE_URL"      # not a local demo store
VERIFY_BROWSER_MISSING = "VERIFY_BROWSER_MISSING"  # Playwright / Chromium not installed
