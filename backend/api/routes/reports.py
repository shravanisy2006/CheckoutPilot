"""Report routes: fetch the results of a previous scan."""

from fastapi import APIRouter, HTTPException

from backend.services.scan_service import get_report

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/{scan_id}")
def read_report(scan_id: str) -> dict:
    """Return the report for one scan.

    Returns HTTP 404 when the requested scan_id does not exist.
    """
    record = get_report(scan_id)
    if record.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=record["message"])
    return record
