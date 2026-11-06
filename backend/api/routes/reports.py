"""Report routes: fetch the results of a previous scan."""

from fastapi import APIRouter

from backend.services.scan_service import get_report

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/{scan_id}")
def read_report(scan_id: str) -> dict:
    """Return the report for one scan. Currently a placeholder."""
    return get_report(scan_id)
