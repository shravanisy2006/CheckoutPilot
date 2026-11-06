"""
Sandbox purchase verification.

Goal: run a store's checkout with a PayPal Sandbox buyer account, complete a
test purchase, and confirm through the Orders API that payment was captured.
Run it before and after an upgrade to produce a before/after comparison.

STATUS: placeholder only. No browser automation or PayPal calls yet.
"""


def verify_checkout(store_url: str, label: str = "before") -> dict:
    """
    Complete a sandbox test purchase on a store and report the result.

    Args:
        store_url: URL of the store (original or upgraded version).
        label: "before" or "after", used to name screenshots in the report.

    Returns:
        {
            "store_url": str,
            "label": str,
            "purchase_succeeded": bool,
            "order_id": str,
            "payment_saved": bool,      # True if a saved PayPal account was created
            "screenshots": list[str],
        }
    """
    # TODO: use Playwright to add a product to the cart and click the PayPal button.
    # TODO: log in with PAYPAL_SANDBOX_BUYER_EMAIL / PASSWORD from .env and approve.
    # TODO: use paypal_integration.PayPalClient.get_order() to confirm the capture.
    # TODO: if the PayPal pop-up is too flaky to automate, fall back to
    #       creating and capturing the order via the Orders API.
    return {
        "store_url": store_url,
        "label": label,
        "purchase_succeeded": False,
        "order_id": "",
        "payment_saved": False,
        "screenshots": [],
    }


def compare_runs(before: dict, after: dict) -> dict:
    """
    Summarise the difference between a 'before' and 'after' verification.

    TODO: highlight improvements (e.g. saved account now created).
    """
    return {"before": before, "after": after, "summary": "Not compared yet"}
