"""
URL validation and sanitization for the CheckoutPilot scanner.
Validates HTTP/HTTPS schemes and rejects malformed or unsupported inputs.
"""

from urllib.parse import urlparse

from scanner.exceptions import InvalidURLError

SUPPORTED_SCHEMES = ("http", "https")


def validate_url(url: str) -> str:
    """
    Validate that an input string is a valid HTTP or HTTPS store URL.

    Args:
        url: The URL string to validate.

    Returns:
        The cleaned/normalized URL string.

    Raises:
        InvalidURLError: If the URL is empty, not a string, has an unsupported scheme,
                         or is malformed.
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

