"""Shared exception classes used across CheckoutPilot modules.

This module defines the shared ``ModuleError`` that other modules (such as
``ai_engine`` and ``paypal_integration``) can import instead of maintaining
their own local fallback copies.

Example:
    from backend.schemas.models import ModuleError
    raise ModuleError("SCAN_FAILED", "The scanner did not return any pages.")
"""


class ModuleError(Exception):
    """An expected, user-explainable failure inside a module.

    Attributes:
        code: A short, stable error code (e.g. "SCAN_FAILED").
        message: A human-readable explanation of the failure.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
