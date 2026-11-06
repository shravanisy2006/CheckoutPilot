"""
Business impact ranking.

Takes the gaps found by ai_engine and sorts them so the merchant sees the
most valuable fix first.

IMPORTANT: impact estimates must be shown as clearly labelled ASSUMPTIONS
based on PayPal's published figures - never as measured results for the store.

STATUS: placeholder only. No ranking algorithm yet.
"""


def rank_gaps(gaps: list[dict]) -> list[dict]:
    """
    Sort gaps from highest to lowest expected business impact.

    Args:
        gaps: Output of ai_engine.analyze_checkout().

    Returns:
        The same gaps, each with an added "estimated_impact" text, sorted by priority.
    """
    # TODO: assign a score to each gap using estimate_impact().
    # TODO: sort gaps by score, highest first.
    return [{**gap, "estimated_impact": estimate_impact(gap)} for gap in gaps]


def estimate_impact(gap: dict) -> str:
    """
    Return a short, human-readable impact estimate for one gap.

    TODO: map each gap_id to an assumption with its source, for example
          "Saved PayPal accounts convert at 95%+ (PayPal earnings call)".
    """
    return "Not estimated yet"
