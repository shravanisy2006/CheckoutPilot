"""Scan routes: start a checkout audit for a store URL."""

from fastapi import APIRouter

from backend.schemas.scan import ScanRequest, ScanResponse
from backend.services.scan_service import run_scan

router = APIRouter(prefix="/scan", tags=["Scan"])


@router.post("", response_model=ScanResponse)
def start_scan(request: ScanRequest) -> ScanResponse:
    """Start a checkout audit scan for the given store URL."""
    return run_scan(request)
