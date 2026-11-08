"""
Custom exception hierarchy for the CheckoutPilot scanner module.
"""


class ScannerError(Exception):
    """Base exception for all scanner-related errors."""


class InvalidURLError(ScannerError, ValueError):
    """Raised when a store URL is invalid, malformed, or has an unsupported scheme."""


class BrowserLaunchError(ScannerError, RuntimeError):
    """Raised when Playwright or Chromium fails to launch, initialize, or connect."""


class BrowserNavigationError(ScannerError, RuntimeError):
    """Raised when the browser encounters a fatal network or navigation failure."""


class BrowserCleanupError(ScannerError):
    """Raised when browser resources fail to close or release cleanly."""

