"""
Business impact ranking.

Takes CheckoutIssue dicts from the AI engine and orders them so the merchant
sees the most valuable fix first.

Score formula (0-100):
    raw   = severity weight x category weight x confidence
    score = round(raw / MAX_RAW x 100)

    severity weight: high 3, medium 2, low 1
    category weight: sdk 1.0, presentment 0.9, vaulting 0.8, mobile 0.7, messaging 0.5
    confidence: 1.0 for rule checks, 0.0-1.0 from the vision model

Ties are broken by severity, then issue_id, so the order is always the same.

Impact text is a clearly labelled ASSUMPTION with a source, never a measured
result for the store (see impact_ranker/assumptions.py).
"""

from impact_ranker.assumptions import get_assumption

SEVERITY_WEIGHTS = {"high": 3, "medium": 2, "low": 1}
CATEGORY_WEIGHTS = {"sdk": 1.0, "presentment": 0.9, "vaulting": 0.8, "mobile": 0.7, "messaging": 0.5}
DEFAULT_CATEGORY_WEIGHT = 0.5
MAX_RAW = max(SEVERITY_WEIGHTS.values()) * max(CATEGORY_WEIGHTS.values())  # 3.0

# Health score: the worst issue costs the most, later issues cost less.
HEALTH_PENALTY_WEIGHTS = (0.40, 0.25, 0.15)  # 1st, 2nd, then every other issue


def _confidence(issue: dict) -> float:
    """Confidence between 0 and 1; missing means 1.0 (rule checks)."""
    try:
        value = float(issue.get("confidence", 1.0))
    except (TypeError, ValueError):
        value = 1.0
    return min(max(value, 0.0), 1.0)


def score_issue(issue: dict) -> int:
    """Return the 0-100 impact score for one issue."""
    severity = SEVERITY_WEIGHTS.get(issue.get("severity", "low"), 1)
    category = CATEGORY_WEIGHTS.get(issue.get("category", ""), DEFAULT_CATEGORY_WEIGHT)
    raw = severity * category * _confidence(issue)
    return round(raw / MAX_RAW * 100)


def rank_issues(issues: list[dict]) -> list[dict]:
    """
    Sort issues from highest to lowest expected impact.

    Args:
        issues: CheckoutIssue dicts from ai_engine.analyze_checkout().

    Returns:
        RankedIssue dicts: each original issue plus an "impact" dict
        (ImpactScore: issue_id, score, rank, rationale, assumption,
        assumption_source), sorted by rank (1 = most important).
        The input list is not modified.
    """
    scored = [(score_issue(issue), issue) for issue in issues]
    scored.sort(
        key=lambda pair: (
            -pair[0],
            -SEVERITY_WEIGHTS.get(pair[1].get("severity", "low"), 1),
            str(pair[1].get("issue_id", "")),
        )
    )

    ranked: list[dict] = []
    for rank, (score, issue) in enumerate(scored, start=1):
        issue_id = issue.get("issue_id", "unknown")
        ranked.append(
            {
                **issue,
                "impact": {
                    "issue_id": issue_id,
                    "score": score,
                    "rank": rank,
                    **get_assumption(issue_id),
                },
            }
        )
    return ranked


def health_score(ranked: list[dict]) -> int:
    """
    Overall checkout health from 0 (many serious issues) to 100 (no issues).

    health = 100 - (0.40 x 1st score + 0.25 x 2nd score + 0.15 x each other score),
    clamped to 0-100. Pass the output of rank_issues().
    """
    scores = sorted((item.get("impact", {}).get("score", score_issue(item)) for item in ranked), reverse=True)
    penalty = 0.0
    for position, score in enumerate(scores):
        weight = HEALTH_PENALTY_WEIGHTS[min(position, len(HEALTH_PENALTY_WEIGHTS) - 1)]
        penalty += weight * score
    return int(min(100, max(0, round(100 - penalty))))


# ---------------------------------------------------------------------------
# Temporary compatibility with the old boilerplate (backend still calls
# rank_gaps and expects "gap_id" + "estimated_impact"). Remove once Member 2
# switches backend/services/scan_service.py to rank_issues().
# ---------------------------------------------------------------------------
def rank_gaps(gaps: list[dict]) -> list[dict]:
    """Deprecated: use rank_issues(). Kept so the current backend keeps working."""
    issues = [{**gap, "issue_id": gap.get("issue_id") or gap.get("gap_id", "unknown")} for gap in gaps]
    result = []
    for item in rank_issues(issues):
        result.append(
            {
                **item,
                "gap_id": item["issue_id"],
                "estimated_impact": f"Score {item['impact']['score']}/100 - {item['impact']['assumption']}",
            }
        )
    return result
