"""
Data models for the Upgrade Planner.
"""

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class PlannedChange:
    """One planned code modification with traceable reasoning."""
    gap_id: str
    file: str                    # Relative file path (e.g. templates/checkout.html)
    target_file: str             # Same as file
    change_summary: str
    line_start: int
    line_end: int
    action: str                  # "replace", "insert", "create_file", "delete"
    before_snippet: str
    after_snippet: str
    rationale: str               # Technical explanation citing PayPal v6 SDK docs
    estimated_impact: str        # Expected business conversion impact
    syntax_type: str             # "html", "javascript", "python", "css"
    priority: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
