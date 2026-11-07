"""
Prompts for the vision model.

The model may only report issues from a fixed list (VISION_ISSUE_CATALOGUE),
so its answers can be validated, de-duplicated against the rule checks, and
ranked consistently. Change PROMPT_VERSION whenever the prompt changes, so
cached answers from the old prompt are not reused.
"""

PROMPT_VERSION = "v1"

# issue_id -> (category, default severity, what it means)
VISION_ISSUE_CATALOGUE: dict[str, tuple[str, str, str]] = {
    "paypal_button_not_prominent": (
        "presentment",
        "medium",
        "The PayPal button is small, low-contrast, or visually less prominent than other payment options.",
    ),
    "paypal_button_cluttered": (
        "presentment",
        "low",
        "The area around the PayPal button is crowded or confusing.",
    ),
    "no_paypal_on_cart": (
        "presentment",
        "high",
        "A cart page screenshot shows no PayPal button at all.",
    ),
    "button_below_fold_mobile": (
        "mobile",
        "medium",
        "On a mobile screenshot, the PayPal button is not visible without scrolling.",
    ),
    "checkout_layout_cramped_mobile": (
        "mobile",
        "low",
        "The mobile checkout layout is cramped, overlapping, or hard to tap.",
    ),
}

SYSTEM_PROMPT = (
    "You are a checkout user-experience auditor for PayPal merchants. "
    "You look at screenshots of an online store's cart and checkout pages and report "
    "only problems that make the PayPal payment option harder to find or use. "
    "You reply with JSON only, no prose, no markdown."
)


def build_user_prompt(screenshot_labels: list[str]) -> str:
    """
    Build the instruction text sent alongside the screenshots.

    Args:
        screenshot_labels: One label per image, in the same order, e.g. "cart (desktop)".
    """
    catalogue_lines = "\n".join(
        f'- "{issue_id}" (category: {category}): {meaning}'
        for issue_id, (category, _severity, meaning) in VISION_ISSUE_CATALOGUE.items()
    )
    image_lines = "\n".join(f"Image {i}: {label}" for i, label in enumerate(screenshot_labels))

    return f"""The images are, in order:
{image_lines}

Report problems using ONLY these issue_id values:
{catalogue_lines}

Rules:
- Only report a problem you can clearly see in the images. If unsure, leave it out.
- Report each issue_id at most once.
- severity must be "high", "medium" or "low".
- confidence is a number from 0.0 to 1.0.
- screenshot_index is the number of the image that best shows the problem.
- If there are no problems, return an empty list.

Return exactly this JSON shape and nothing else:
{{"issues": [{{"issue_id": "...", "title": "short title", "severity": "medium",
"evidence": "one sentence describing what you see", "confidence": 0.8,
"screenshot_index": 0}}]}}"""


RETRY_NOTE = (
    "Your previous reply could not be used because it was not valid JSON in the required "
    "shape. Reply again with ONLY the JSON object, using only the allowed issue_id values."
)
