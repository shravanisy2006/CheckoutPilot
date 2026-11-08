"""
Checkout scanner: walks a store's checkout in a headless browser and collects raw data.
"""

from scanner.browser import BrowserConfig, PlaywrightBrowserSession
from scanner.checkout_scanner import (
    async_scan_store,
    detect_paypal_scripts,
    detect_paypal_sdk_version,
    scan_store,
)
from scanner.exceptions import (
    BrowserCleanupError,
    BrowserLaunchError,
    BrowserNavigationError,
    InvalidURLError,
    ScannerError,
)
from scanner.navigator import StoreNavigator
from scanner.paypal_detector import (
    detect_overall_sdk_version,
    detect_paypal_elements,
    filter_paypal_scripts,
    is_paypal_script,
    parse_script_details,
)
from scanner.selectors import NavigationSelectors
from scanner.url_validator import is_valid_url, validate_url

__all__ = [
    "scan_store",
    "async_scan_store",
    "detect_paypal_scripts",
    "detect_paypal_sdk_version",
    "validate_url",
    "is_valid_url",
    "ScannerError",
    "InvalidURLError",
    "BrowserLaunchError",
    "BrowserNavigationError",
    "BrowserCleanupError",
    "BrowserConfig",
    "PlaywrightBrowserSession",
    "NavigationSelectors",
    "StoreNavigator",
    "parse_script_details",
    "is_paypal_script",
    "detect_overall_sdk_version",
    "filter_paypal_scripts",
    "detect_paypal_elements",
]
