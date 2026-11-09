"""
Knowledge base and rationale generator for PayPal checkout upgrades.
"""

MIGRATION_RATIONALES = {
    "sdk_outdated": {
        "technical": (
            "PayPal JS SDK v5 ('paypal.com/sdk/js') is deprecated in favor of JS SDK v6 "
            "('web-sdk/v6/core'). SDK v6 utilizes web components (<paypal-button>), integrates "
            "browser-safe client tokens, and enables fast one-time payment sessions that preload payment methods."
        ),
        "impact": "Reduces checkout load latency by up to 40% and enables biometric/saved account authentication.",
    },
    "no_paypal_on_cart": {
        "technical": (
            "Shoppers currently must fill out long shipping forms before viewing PayPal. "
            "Adding an express <paypal-button> directly to 'templates/cart.html' allows shoppers "
            "to authenticate and provide shipping/billing info in one seamless flow."
        ),
        "impact": "Expected 20-30% reduction in cart abandonment by skipping multi-step checkout forms.",
    },
    "button_below_fold_mobile": {
        "technical": (
            "On mobile viewports (<=760px), single-column DOM rendering places the long shipping form "
            "ahead of the order summary and PayPal button container. Using CSS grid template areas "
            "('.checkout.upgraded { grid-template-areas: \"summary\" \"form\"; }') visually elevates the payment button "
            "above the fold without disrupting DOM hierarchy."
        ),
        "impact": "Decreases mobile drop-off by up to 15% by making payment options visible immediately upon load.",
    },
    "missing_client_token": {
        "technical": (
            "The v6 SDK requires a short-lived access token generated server-side via PayPal's "
            "v1/oauth2/token or identity endpoints. Adding 'GET /api/paypal/client-token' allows the browser "
            "to initialize the v6 SDK securely without exposing merchant client secrets."
        ),
        "impact": "Enables zero-trust client security and activates eligible payment methods dynamically.",
    },
}


def get_rationale(gap_id: str) -> tuple[str, str]:
    """Return (technical_rationale, business_impact) for a given gap ID."""
    info = MIGRATION_RATIONALES.get(gap_id)
    if info:
        return info["technical"], info["impact"]
    return (
        f"Automated upgrade to resolve checkout gap '{gap_id}' in accordance with PayPal modern standards.",
        "Improves checkout experience and reduces payment friction.",
    )

