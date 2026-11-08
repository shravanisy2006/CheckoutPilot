"""
PayPal integration evidence collector for CheckoutPilot scanner.
Extracts facts about loaded scripts, SDK versions, button/container elements,
Pay Later messaging, and viewport positions without drawing evaluative conclusions.
"""

from urllib.parse import parse_qs, urlparse
from typing import Any
from playwright.async_api import Page
from scanner.selectors import NavigationSelectors

PAYPAL_HOST_PATTERNS = (
    "paypal.com",
    "paypalobjects.com",
    "braintreegateway.com",
    "braintree-api.com",
)


def _hostname_is_paypal(hostname: str) -> bool:
    """Return True if hostname is an exact PayPal/Braintree host or a legitimate subdomain."""
    hostname = hostname.lower()
    for pattern in PAYPAL_HOST_PATTERNS:
        if hostname == pattern or hostname.endswith("." + pattern):
            return True
    return False


def is_paypal_script(url: str) -> bool:
    """
    Check if a script URL belongs to PayPal or Braintree.

    Matches exact trusted hostnames (paypal.com, paypalobjects.com,
    braintreegateway.com, braintree-api.com) and their legitimate
    subdomains. Broad substring matching is intentionally avoided to
    prevent false positives (e.g. paypal.evil.com or evil.com/paypal).
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if _hostname_is_paypal(hostname):
            return True
    except Exception:
        pass
    return False



def parse_script_details(url: str) -> dict[str, Any]:
    """
    Inspect a script URL and extract PayPal SDK version and requested components.

    Returns:
        {
            "url": str,
            "is_paypal": bool,
            "sdk_version": "v4" | "v5" | "v6" | "unknown" | None,
            "components": list[str],
        }
    """
    is_pp = is_paypal_script(url)
    if not is_pp:
        return {
            "url": url,
            "is_paypal": False,
            "sdk_version": None,
            "components": [],
        }

    url_lower = url.lower()
    sdk_version = "unknown"
    components: list[str] = []

    try:
        parsed = urlparse(url)
        path_lower = (parsed.path or "").lower()
        query_params = parse_qs(parsed.query)

        # 1. Detect Web SDK v6
        if (
            "web-sdk/v6" in path_lower
            or "web-sdk" in path_lower
            or "@paypal/web-sdk" in url_lower
            or "/v6/" in path_lower
        ):
            sdk_version = "v6"

        # 2. Detect JavaScript SDK v5 (paypal.com/sdk/js)
        elif "paypal.com/sdk/js" in url_lower or path_lower.endswith("/sdk/js"):
            sdk_version = "v5"
            # Extract requested components (e.g. buttons, messages, marks)
            if "components" in query_params:
                raw_comps = query_params["components"][0]
                components = [c.strip().lower() for c in raw_comps.split(",") if c.strip()]
            else:
                # Default SDK v5 component when omitted is 'buttons'
                components = ["buttons"]

        # 3. Detect legacy checkout.js (v4)
        elif "checkout.js" in path_lower:
            sdk_version = "v4"

        # 4. Other PayPal scripts (e.g. pptm.js tag manager) remain 'unknown'
        else:
            sdk_version = "unknown"

    except Exception:
        sdk_version = "unknown"

    return {
        "url": url,
        "is_paypal": True,
        "sdk_version": sdk_version,
        "components": components,
    }


def detect_overall_sdk_version(scripts: list[str]) -> str:
    """
    Determine the primary PayPal JavaScript SDK version present across all script URLs.

    Returns:
        "v6" if Web SDK v6 is detected.
        "v5" if JS SDK v5 is detected.
        "v4" if legacy checkout.js is detected.
        "unknown" if no version could be determined or no PayPal SDK was found.
        Never guesses versions.
    """
    detected_versions = set()
    for script_url in scripts:
        details = parse_script_details(script_url)
        if details["is_paypal"] and details["sdk_version"] in ("v4", "v5", "v6"):
            detected_versions.add(details["sdk_version"])

    # Prioritize newest detected version if multiple co-exist
    if "v6" in detected_versions:
        return "v6"
    if "v5" in detected_versions:
        return "v5"
    if "v4" in detected_versions:
        return "v4"

    return "unknown"


def filter_paypal_scripts(scripts: list[str]) -> list[str]:
    """Return all unique script URLs that belong to PayPal."""
    results = [s for s in scripts if is_paypal_script(s)]
    return sorted(list(set(results)))


PAY_LATER_MESSAGING_SELECTORS = [
    "paypal-messages",
    "[data-pp-message]",
    "[data-pp-type]",
    ".paypal-msg",
    ".paypal-message",
    "[id*='paypal-message' i]",
    "[class*='paypal-message' i]",
    "iframe[title*='PayPal Message' i]",
    "iframe[src*='credit-presentment' i]",
    "iframe[src*='upstream/bizcomponents/messages' i]",
]


async def detect_paypal_elements(
    page: Page,
    selectors: NavigationSelectors | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Inspect the page for PayPal buttons, containers, and Pay Later messaging components.

    Returns:
        Tuple of:
          - paypal_elements: list of detected element dictionaries with bounding box and visibility.
          - pay_later_messaging: dictionary describing detected messaging components without assuming
                                 unavailability if missing.
    """
    sel_config = selectors or NavigationSelectors()
    elements: list[dict[str, Any]] = []

    # 1. Detect buttons and container elements
    all_container_selectors = list(sel_config.paypal_containers)
    for sel in all_container_selectors:
        try:
            locators = page.locator(sel)
            count = await locators.count()
            for i in range(min(count, 5)):
                item = locators.nth(i)
                try:
                    is_vis = await item.is_visible()
                    box = await item.bounding_box()
                    tag = await item.evaluate("el => el.tagName.toLowerCase()")
                    elem_id = await item.evaluate("el => el.id || ''")
                    elem_classes = await item.evaluate("el => el.className || ''")

                    category = "container"
                    if "button" in sel or "button" in elem_id.lower() or "button" in str(elem_classes).lower():
                        category = "button"
                    elif "iframe" in sel:
                        category = "iframe"
                    elif "marks" in sel:
                        category = "marks"

                    bounding_box_dict = None
                    if box:
                        bounding_box_dict = {
                            "x": round(box["x"], 1),
                            "y": round(box["y"], 1),
                            "width": round(box["width"], 1),
                            "height": round(box["height"], 1),
                        }

                    elements.append(
                        {
                            "selector": sel,
                            "tag": tag,
                            "id": elem_id,
                            "class": str(elem_classes),
                            "category": category,
                            "visible": is_vis,
                            "bounding_box": bounding_box_dict,
                        }
                    )
                except Exception:
                    continue
        except Exception:
            continue

    # 2. Detect Pay Later messaging components
    messaging_elements: list[dict[str, Any]] = []
    for sel in PAY_LATER_MESSAGING_SELECTORS:
        try:
            locators = page.locator(sel)
            count = await locators.count()
            for i in range(min(count, 5)):
                item = locators.nth(i)
                try:
                    is_vis = await item.is_visible()
                    box = await item.bounding_box()
                    tag = await item.evaluate("el => el.tagName.toLowerCase()")
                    elem_id = await item.evaluate("el => el.id || ''")
                    elem_classes = await item.evaluate("el => el.className || ''")

                    bbox = None
                    if box:
                        bbox = {
                            "x": round(box["x"], 1),
                            "y": round(box["y"], 1),
                            "width": round(box["width"], 1),
                            "height": round(box["height"], 1),
                        }

                    entry = {
                        "selector": sel,
                        "tag": tag,
                        "id": elem_id,
                        "class": str(elem_classes),
                        "visible": is_vis,
                        "bounding_box": bbox,
                    }
                    messaging_elements.append(entry)
                    # Also include in general elements under 'messaging' category
                    elements.append(
                        {
                            "selector": sel,
                            "tag": tag,
                            "id": elem_id,
                            "class": str(elem_classes),
                            "category": "messaging",
                            "visible": is_vis,
                            "bounding_box": bbox,
                        }
                    )
                except Exception:
                    continue
        except Exception:
            continue

    pay_later_info = {
        "detected": len(messaging_elements) > 0,
        "elements_count": len(messaging_elements),
        "elements": messaging_elements,
    }

    return elements, pay_later_info
