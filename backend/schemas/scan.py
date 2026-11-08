"""Request and response models (schemas) for the scan API.

Pydantic validates incoming data automatically and documents it in /docs.
Extend these models as the real features are built.
"""

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    """What the frontend sends to start a scan."""

    store_url: str = Field(..., examples=["https://demo-store.example.com"])
    include_mobile: bool = Field(True, description="Also scan a mobile-sized screen")


class Gap(BaseModel):
    """One checkout problem found in a store."""

    gap_id: str
    title: str
    severity: str = "unknown"  # e.g. "high", "medium", "low"
    description: str = ""  # human-readable summary of the issue
    estimated_impact: str = ""  # filled in by the impact ranker
    impact: dict | None = None  # ranked impact details (score, rank, assumption, ...)
    evidence: str = ""  # raw evidence text from the AI engine
    category: str = ""  # issue category (e.g. "sdk", "presentment", "mobile")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)  # confidence score (0.0-1.0)
    screenshot_path: str = ""  # path to supporting screenshot, if any
    fixable_by_agent: bool = False  # whether the code agent can fix this issue


class ScanResponse(BaseModel):
    """What the backend returns after a scan."""

    store_url: str
    status: str  # e.g. "placeholder", "completed", "failed"
    message: str
    gaps: list[Gap] = Field(default_factory=list)
    scan_id: str = ""
    health_score: int | None = None
    warnings: list[str] = Field(default_factory=list)
