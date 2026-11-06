"""
Request and response models (schemas) for the scan API.

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
    description: str = ""
    estimated_impact: str = ""  # filled in by the impact ranker


class ScanResponse(BaseModel):
    """What the backend returns after a scan."""

    store_url: str
    status: str  # e.g. "placeholder", "completed", "failed"
    message: str
    gaps: list[Gap] = []
