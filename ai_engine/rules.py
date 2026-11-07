"""
Rule-based checkout checks (no AI needed).

Each check reads ScanData (the scanner's output) and returns a list of
CheckoutIssue dictionaries. These checks are deterministic: the same input
always gives the same output, and they keep working if the AI is down.

Checks:
    sdk_outdated              PayPal JS SDK v4 or v5 is loaded
    no_paypal_on_cart         no PayPal element on any cart page
    no_paypal_on_product      no PayPal element on any product page
    button_below_fold_mobile  PayPal button needs scrolling on mobile checkout
"""

# Issues the code agent (Member 5) knows how to fix.
FIXABLE_ISSUES = {"sdk_outdated", "no_paypal_on_cart"}


def make_issue(
    issue_id: str,
    title: str,
    category: str,
    severity: str,
    evidence: str,
    screenshot_path: str = "",
    source: str = "rule",
    confidence: float = 1.0,
) -> dict:
    """Build one CheckoutIssue dictionary in the agreed team format."""
    return {
        "issue_id": issue_id,
        "title": title,
        "category": category,
        "severity": severity,
        "source": source,
        "evidence": evidence,
        "screenshot_path": screenshot_path or "",
        "fixable_by_agent": issue_id in FIXABLE_ISSUES,
        "confidence": confidence,
    }


def get_pages(scan_data: dict, step: str, viewport: str | None = None) -> list[dict]:
    """Return the scanned pages for one checkout step, optionally one viewport."""
    return [
        page
        for page in scan_data.get("pages", []) or []
        if page.get("step") == step and (viewport is None or page.get("viewport") == viewport)
    ]


def _has_paypal(page: dict) -> bool:
    """True if the scanner found at least one PayPal element on the page."""
    return bool(page.get("paypal_elements"))


def _first_screenshot(pages: list[dict]) -> str:
    """Screenshot of the first page in the list (desktop is listed first by the scanner)."""
    for page in pages:
        if page.get("screenshot_path"):
            return page["screenshot_path"]
    return ""


def check_sdk_version(scan_data: dict) -> list[dict]:
    """Flag stores that load an outdated PayPal JavaScript SDK (v4 or v5)."""
    version = scan_data.get("paypal_sdk_version") or "none"
    if version not in ("v4", "v5"):
        return []
    return [
        make_issue(
            "sdk_outdated",
            f"PayPal JavaScript SDK {version} is outdated",
            "sdk",
            "high",
            f"The store loads PayPal JavaScript SDK {version}; PayPal's current version is v6.",
        )
    ]


def check_paypal_on_cart(scan_data: dict) -> list[dict]:
    """Flag stores where no PayPal button appears on any cart page."""
    cart_pages = get_pages(scan_data, "cart")
    if not cart_pages or any(_has_paypal(page) for page in cart_pages):
        return []
    viewports = ", ".join(sorted({page.get("viewport", "unknown") for page in cart_pages}))
    return [
        make_issue(
            "no_paypal_on_cart",
            "PayPal button missing on the cart page",
            "presentment",
            "high",
            f"No PayPal element found on the cart page ({viewports}); "
            "shoppers only see PayPal at the final checkout step.",
            _first_screenshot(cart_pages),
        )
    ]


def check_paypal_on_product(scan_data: dict) -> list[dict]:
    """Flag stores where no PayPal button appears on any product page."""
    product_pages = get_pages(scan_data, "product")
    if not product_pages or any(_has_paypal(page) for page in product_pages):
        return []
    return [
        make_issue(
            "no_paypal_on_product",
            "No PayPal button on the product page",
            "presentment",
            "medium",
            "Shoppers must go to the cart or checkout before PayPal appears.",
            _first_screenshot(product_pages),
        )
    ]


def check_mobile_button_position(scan_data: dict) -> list[dict]:
    """Flag checkouts where every PayPal element is below the fold on mobile."""
    for page in get_pages(scan_data, "checkout", "mobile"):
        elements = page.get("paypal_elements") or []
        if elements and not any(el.get("visible_without_scroll") for el in elements):
            return [
                make_issue(
                    "button_below_fold_mobile",
                    "PayPal button hidden below the fold on mobile",
                    "mobile",
                    "medium",
                    "On a mobile screen the shopper must scroll before the PayPal button appears.",
                    page.get("screenshot_path", ""),
                )
            ]
    return []


# Order matters only for readability; ranking decides the final order.
ALL_CHECKS = (
    check_sdk_version,
    check_paypal_on_cart,
    check_paypal_on_product,
    check_mobile_button_position,
)


def run_rule_checks(scan_data: dict) -> list[dict]:
    """Run every rule check and return all issues found."""
    issues: list[dict] = []
    for check in ALL_CHECKS:
        issues.extend(check(scan_data))
    return issues
