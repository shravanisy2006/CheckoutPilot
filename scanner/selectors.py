"""
Configurable selectors for navigating e-commerce stores.
Prioritizes stable demo store element IDs with fallback selectors for diverse layouts.
"""

from dataclasses import dataclass, field


@dataclass
class NavigationSelectors:
    """Configurable CSS and text selectors for e-commerce checkout navigation."""

    # Product page identification / discovery (when landing on store homepage or catalog)
    product_links: list[str] = field(
        default_factory=lambda: [
            "a[href*='/product']",
            "a[href*='/item']",
            "a[href*='/p/']",
            ".product-card a",
            ".product-item a",
            ".product-title a",
            "[data-testid*='product' i] a",
            ".product a",
        ]
    )

    # Add to Cart triggers
    add_to_cart: list[str] = field(
        default_factory=lambda: [
            "#add-to-cart",  # Stable demo store ID
            "button[id*='add-to-cart' i]",
            "button[name*='add-to-cart' i]",
            "button[data-action*='add-to-cart' i]",
            "button:has-text('Add to Cart')",
            "button:has-text('Add to Bag')",
            "button:has-text('Buy Now')",
            "input[type='submit'][value*='Add to Cart' i]",
            "a:has-text('Add to Cart')",
            "[data-testid*='add-to-cart' i]",
            ".add-to-cart",
        ]
    )

    # Cart navigation triggers
    go_to_cart: list[str] = field(
        default_factory=lambda: [
            "#go-to-cart",  # Stable demo store ID
            "a[href*='/cart']",
            "a[href*='/basket']",
            "a[href*='/bag']",
            "button[id*='cart' i]",
            "a:has-text('View Cart')",
            "a:has-text('Go to Cart')",
            "a:has-text('Cart')",
            "button:has-text('Cart')",
            "[data-testid*='cart' i]",
            ".cart-icon",
            ".view-cart",
        ]
    )

    # Checkout navigation triggers
    go_to_checkout: list[str] = field(
        default_factory=lambda: [
            "#go-to-checkout",  # Stable demo store ID
            "a[href*='/checkout']",
            "button[id*='checkout' i]",
            "button[name*='checkout' i]",
            "button:has-text('Checkout')",
            "a:has-text('Checkout')",
            "button:has-text('Proceed to Checkout')",
            "a:has-text('Proceed to Checkout')",
            "input[value*='Checkout' i]",
            "[data-testid*='checkout' i]",
            ".checkout-button",
        ]
    )

    # PayPal container and button elements
    paypal_containers: list[str] = field(
        default_factory=lambda: [
            "#paypal-button-container",  # Stable demo store ID
            "[data-funding-source='paypal']",
            "iframe[src*='paypal.com']",
            "iframe[name*='paypal']",
            ".paypal-button",
            "[id*='paypal-button' i]",
            "[class*='paypal-button' i]",
            "paypal-marks",
            "paypal-messages",
            "[data-paypal-button]",
        ]
    )
