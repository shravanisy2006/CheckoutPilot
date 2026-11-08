"""
URL validation and sanitization for the CheckoutPilot scanner.
Validates HTTP/HTTPS schemes and rejects malformed or unsupported inputs.
Provides SSRF protection by rejecting private, loopback, link-local,
multicast, and reserved IP addresses unless explicitly allowed.
"""

import ipaddress
import os
from urllib.parse import urlparse

from scanner.exceptions import InvalidURLError

SUPPORTED_SCHEMES = ("http", "https")

# Explicit opt-in for scanning localhost/private addresses.
# Defaults to false so production deployments are never accidentally
# exposed to SSRF via the scanner. Set to "true" only in controlled
# development/test environments that need to scan local demo stores.
# Even when true, ONLY loopback addresses (localhost/127.0.0.1/::1) are
# permitted; all other private/reserved addresses remain blocked.
ALLOW_LOCALHOST_SCANS = (
    os.getenv("ALLOW_LOCALHOST_SCANS", "false").strip().lower() in ("1", "true", "yes")
)


def _is_private_or_reserved_host(hostname: str) -> bool:
    """Return True if hostname is a literal non-public IP address or "localhost".

    Covers loopback, private, link-local, multicast, reserved, and
    unspecified IPv4/IPv6 addresses, plus the literal "localhost" name.
    Domain names (which require DNS resolution) return False here; they
    are allowed through but should be rechecked at navigation time
    (see navigator route blocking).
    """
    if hostname.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False  # domain name — not a literal IP, defer to navigator
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _is_loopback_host(hostname: str) -> bool:
    """Return True if hostname is a loopback address (127.0.0.0/8, ::1, localhost)."""
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_loopback
    except ValueError:
        # Domain name: allow only the literal "localhost" name
        return hostname.lower() == "localhost"


def _localhost_scans_enabled() -> bool:
    """Return True if localhost scanning is explicitly enabled via env var.

    Reads ALLOW_LOCALHOST_SCANS from os.environ at call time so that
    monkeypatch.setenv works correctly in tests. Defaults to False.
    """
    return os.getenv("ALLOW_LOCALHOST_SCANS", "false").strip().lower() in ("1", "true", "yes")


def validate_url(url: str) -> str:
    """
    Validate that an input string is a valid HTTP or HTTPS store URL.

    Args:
        url: The URL string to validate.

    Returns:
        The cleaned/normalized URL string.

    Raises:
        InvalidURLError: If the URL is empty, not a string, has an unsupported scheme,
                         is malformed, or points to a private/reserved address
                         without ALLOW_LOCALHOST_SCANS=true.
    """
    if not isinstance(url, str):
        raise InvalidURLError(f"Store URL must be a string, got {type(url).__name__}.")

    cleaned = url.strip()
    if not cleaned:
        raise InvalidURLError("Store URL cannot be empty or whitespace.")

    try:
        parsed = urlparse(cleaned)
    except Exception as exc:
        raise InvalidURLError(f"Malformed store URL: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if not scheme:
        raise InvalidURLError(
            f"Missing URL scheme in '{cleaned}'. Store URL must start with 'http://' or 'https://'."
        )

    if scheme not in SUPPORTED_SCHEMES:
        raise InvalidURLError(
            f"Unsupported scheme '{parsed.scheme}' in '{cleaned}'. Only HTTP and HTTPS are supported."
        )

    netloc = parsed.netloc.strip()
    if not netloc:
        raise InvalidURLError(f"Missing domain or host in store URL '{cleaned}'.")

    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError(f"Store URL '{cleaned}' does not contain a valid hostname.")

    # Disallow invalid host characters (spaces, line breaks, control characters)
    if any(char in hostname for char in (" ", "\t", "\r", "\n", "\\", "<", ">", '"', "'")):
        raise InvalidURLError(f"Invalid characters in store URL hostname: '{hostname}'.")

    # SSRF protection: reject all non-public IP addresses.
    if _is_private_or_reserved_host(hostname):
        if not _localhost_scans_enabled():
            raise InvalidURLError(
                f"Private or reserved hostname not allowed: '{hostname}'. "
                "Set ALLOW_LOCALHOST_SCANS=true only in controlled dev/test environments."
            )
        # Even when localhost scans are allowed, ONLY loopback is permitted.
        # Private IPv4/IPv6, link-local, multicast, reserved, unspecified,
        # and cloud metadata addresses remain blocked.
        if not _is_loopback_host(hostname):
            raise InvalidURLError(
                f"Private or reserved hostname not allowed even with localhost scans: '{hostname}'."
            )

    return cleaned


def is_valid_url(url: str) -> bool:
    """
    Check if a URL is valid without raising an exception.

    Args:
        url: The URL string to test.

    Returns:
        True if valid HTTP/HTTPS URL, False otherwise.
    """
    try:
        validate_url(url)
        return True
    except (InvalidURLError, TypeError):
        return False
