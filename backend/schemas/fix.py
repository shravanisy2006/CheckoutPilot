"""Request and response models for the fix API (FIX step).

Follows the API contract in docs/api_contract.md.
"""

from pydantic import BaseModel, Field


class FixRequest(BaseModel):
    """What the frontend sends to start a fix."""

    scan_id: str = Field(..., examples=["scan_20261108_132000_ab12"])
    issue_ids: list[str] = Field(..., examples=[["sdk_outdated", "no_paypal_on_cart"]])


class FixExplanation(BaseModel):
    """Explanation of one fix."""

    issue_id: str
    what_changed: str
    files: list[str]


class FixFile(BaseModel):
    """One file changed by the fix."""

    path: str
    change_type: str  # "modified", "added", "deleted"
    diff: str  # unified diff text
    lines_added: int
    lines_removed: int


class FixResponse(BaseModel):
    """What the backend returns after a fix."""

    fix_id: str
    scan_id: str
    status: str  # "proposed", "verified", "approved", "rejected"
    issue_ids: list[str]
    summary: str
    explanation: list[FixExplanation] = Field(default_factory=list)
    files: list[FixFile] = Field(default_factory=list)
    branch: str = ""
    pr_url: str = ""
    patched_store_dir: str = ""
