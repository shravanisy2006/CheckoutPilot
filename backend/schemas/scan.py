"""Request and response models (schemas) for the scan API.

Pydantic validates incoming data automatically and documents it in /docs.
Extends these models as the real features are built.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    """What the frontend sends to start a scan."""

    store_url: str = Field(..., examples=["https://demo-store.example.com"])
    include_mobile: bool = Field(True, description="Also scan a mobile-sized screen")


class Impact(BaseModel):
    """Ranked impact details for a single issue."""

    issue_id: str
    score: int  # 0-100
    rank: int
    rationale: str
    assumption: str
    assumption_source: str


class Gap(BaseModel):
    """One checkout problem found in a store."""

    issue_id: str
    title: str
    category: str = "unknown"  # e.g. "sdk", "presentment", "mobile", "vaulting", "messaging"
    severity: str = "unknown"  # e.g. "high", "medium", "low"
    source: str = "rule"  # "rule", "vision", or "rule+vision"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)  # confidence score (0.0-1.0)
    evidence: str = ""  # raw evidence text from the AI engine
    screenshot_url: str = ""  # path to supporting screenshot, if any
    fixable_by_agent: bool = False  # whether the code agent can fix this issue
    impact: Impact | None = None  # ranked impact details (score, rank, assumption, ...)


class ScanResponse(BaseModel):
    """What the backend returns after a scan."""

    store_url: str
    scanned_at: str  # ISO timestamp when the scan ran
    status: str  # "completed", "partial", "failed"
    message: str  # Human-readable message about the scan result
    paypal_sdk_version: str = "none"  # "v4", "v5", "v6", "none"
    health_score: int | None = None  # 0-100
    health_label: str = ""  # "poor" (<50), "fair" (50-79), "good" (80+)
    issue_counts: dict[str, int] = Field(default_factory=lambda: {"high": 0, "medium": 0, "low": 0})
    issues: list[Gap] = Field(default_factory=list)
    pages: list[dict] = Field(default_factory=list)
    scan_id: str = ""
    warnings: list[str] = Field(default_factory=list)
    # {"text": "...", "generated_by": "ai" | "template"}: a short summary for the store owner.
    owner_summary: dict = Field(default_factory=dict)