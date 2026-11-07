"""
Labelled assumptions behind each impact score.

Every assumption names its source and says plainly that the effect has NOT
been measured for the scanned store. Only figures PayPal has published are
quoted; where no published figure exists, the text says it is a general
heuristic. Do not add numbers here without a source you have checked.
"""

PAYPAL_EARNINGS_Q4_2025 = "PayPal Q4 2025 earnings call"
PAYPAL_SDK_UPGRADE_GUIDE = "PayPal developer docs: Upgrade from JavaScript SDK v5 to v6"
NOT_MEASURED = "Effect not measured for this store."

# issue_id -> (rationale, assumption text, source)
ASSUMPTIONS: dict[str, tuple[str, str, str]] = {
    "sdk_outdated": (
        "The store cannot use PayPal's current checkout features until it moves to SDK v6.",
        "PayPal's newer checkout features are built on JavaScript SDK v6.",
        PAYPAL_SDK_UPGRADE_GUIDE,
    ),
    "no_paypal_on_cart": (
        "Shoppers cannot choose one-click PayPal until the final checkout step.",
        "Saved PayPal accounts convert at over 95% on average when used as the default.",
        PAYPAL_EARNINGS_Q4_2025,
    ),
    "no_paypal_on_product": (
        "Shoppers ready to buy must add to cart and continue before PayPal appears.",
        "Saved PayPal accounts convert at over 95% on average when used as the default.",
        PAYPAL_EARNINGS_Q4_2025,
    ),
    "button_below_fold_mobile": (
        "Mobile shoppers must scroll to find the PayPal button.",
        "A payment option that is not visible without scrolling is likely to be used less.",
        "General usability heuristic (no published PayPal figure)",
    ),
    "paypal_button_not_prominent": (
        "The PayPal option is visually weaker than other payment options.",
        "A less prominent payment option is likely to be chosen less often.",
        "General usability heuristic (no published PayPal figure)",
    ),
    "paypal_button_cluttered": (
        "The area around the PayPal button is crowded or confusing.",
        "Visual clutter near the payment step can slow shoppers down.",
        "General usability heuristic (no published PayPal figure)",
    ),
    "checkout_layout_cramped_mobile": (
        "The mobile checkout is cramped or hard to tap.",
        "Hard-to-tap mobile layouts make completing checkout harder.",
        "General usability heuristic (no published PayPal figure)",
    ),
}

DEFAULT_ASSUMPTION = (
    "This issue may make PayPal checkout harder to find or use.",
    "Impact estimated from the issue's severity and category only.",
    "CheckoutPilot scoring rules",
)


def get_assumption(issue_id: str) -> dict:
    """
    Return the rationale and a labelled assumption string for one issue.

    Returns:
        {"rationale": str, "assumption": str, "assumption_source": str}
        The assumption string always names its source and states that the
        effect is not measured for this store.
    """
    rationale, text, source = ASSUMPTIONS.get(issue_id, DEFAULT_ASSUMPTION)
    return {
        "rationale": rationale,
        "assumption": f"{text} ({source}). {NOT_MEASURED}",
        "assumption_source": source,
    }
