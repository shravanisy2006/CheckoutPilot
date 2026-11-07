"""Errors raised by the PayPal integration module."""

try:  # use the team's shared error class once it exists
    from backend.schemas.models import ModuleError  # type: ignore
except ImportError:  # pragma: no cover - fallback until the shared class lands
    class ModuleError(Exception):
        """An expected, user-explainable failure inside a module."""

        def __init__(self, code: str, message: str) -> None:
            super().__init__(f"{code}: {message}")
            self.code = code
            self.message = message


PAYPAL_NOT_CONFIGURED = "PAYPAL_NOT_CONFIGURED"   # client ID / secret missing in .env
PAYPAL_LIVE_BLOCKED = "PAYPAL_LIVE_BLOCKED"       # someone pointed us at the Live API
PAYPAL_AUTH_FAILED = "PAYPAL_AUTH_FAILED"         # wrong client ID / secret
PAYPAL_UNAVAILABLE = "PAYPAL_UNAVAILABLE"         # network problem or PayPal 5xx
PAYPAL_REQUEST_FAILED = "PAYPAL_REQUEST_FAILED"   # PayPal rejected the request (4xx)
