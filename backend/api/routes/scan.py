"""Scan routes: start a checkout audit for a store URL."""

from fastapi import APIRouter

from backend.schemas.scan import ScanRequest, ScanResponse
from backend.services.scan_service import run_scan

router = APIRouter(prefix="/scan", tags=["Scan"])


@router.post("", response_model=ScanResponse)
def start_scan(request: ScanRequest) -> ScanResponse:
    """Scan a store's PayPal checkout (FIND step).

    Opens the store in a real browser (product, cart and checkout pages, desktop and
    mobile), checks the PayPal SDK version and button placement with rule checks and
    an AI vision model, and returns the issues ranked by impact plus a 0-100 health
    score. Takes about 10-60 seconds. Example body: `{"store_url": "http://localhost:8101"}`.
    """
    return run_scan(request)
