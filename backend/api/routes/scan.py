"""Scan routes: start a checkout audit for a store URL."""

from fastapi import APIRouter

from backend.schemas.scan import ScanRequest, ScanResponse
from backend.services.scan_service import run_scan

router = APIRouter(prefix="/scan", tags=["Scan"])


@router.post("", response_model=ScanResponse)
def start_scan(request: ScanRequest) -> ScanResponse:
    """Start a scan. Currently returns placeholder results."""
    return run_scan(request)
