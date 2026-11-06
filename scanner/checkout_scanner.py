"""
Checkout scanner (Playwright).

Goal: open a store like a shopper would - product page -> cart -> checkout -
and record what the PayPal checkout looks like at each step.

Output of this module is a plain dictionary (see `scan_store`) so that the
ai_engine module can use it without importing anything from here.

STATUS: placeholder only. No browser automation yet.
"""


def scan_store(store_url: str, include_mobile: bool = True) -> dict:
    """
    Walk the store's checkout and collect raw data.

    Args:
        store_url: Public URL of the store to scan.
        include_mobile: If True, also scan with a mobile screen size.

    Returns:
        A dictionary shaped like:
        {
            "store_url": str,
            "pages": [
                {
                    "step": "product" | "cart" | "checkout",
                    "viewport": "desktop" | "mobile",
                    "screenshot_path": str,
                    "html": str,
                    "scripts": list[str],          # URLs of loaded scripts
                    "paypal_elements": list[dict], # position/size of PayPal buttons
                }
            ],
        }
    """
    # TODO: launch Playwright (chromium) in headless mode.
    # TODO: open store_url, find a product, add it to the cart, go to checkout.
    # TODO: at each step, save a screenshot, the page HTML and loaded script URLs.
    # TODO: record the position of every PayPal button/element on the page.
    # TODO: repeat with a mobile viewport when include_mobile is True.
    return {"store_url": store_url, "pages": []}


def detect_paypal_scripts(scripts: list[str]) -> list[str]:
    """
    Return only the script URLs that belong to PayPal.

    TODO: filter for PayPal SDK URLs (e.g. paypal.com/sdk/js, web-sdk/v6/core, checkout.js).
    """
    return []
