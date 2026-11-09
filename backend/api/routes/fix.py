"""Fix routes: the code agent writes the PayPal checkout upgrade (FIX step)."""

from fastapi import APIRouter, HTTPException

from backend.schemas.fix import FixRequest
from backend.schemas.models import ModuleError
from backend.services import fix_service

router = APIRouter(prefix="/fix", tags=["Fix"])

_STATUS = {fix_service.FIX_BUSY: 409, fix_service.FIX_FAILED: 500}


@router.post("")
def fix(request: FixRequest) -> dict:
    """Write the upgrade (PayPal SDK v5 -> v6, cart button, mobile layout) on a copy of the store.

    Example body: `{"store": "legacy"}` or `{"scan_id": "<id from /api/scan>", "issue_ids": [...]}`.
    The original store is never changed; the patched copy is in `patched_store_dir`.
    Response shape: docs/sample_result.json -> "fix", plus `generated_by` ("ai+template" or "template").
    Then call POST /api/verify with `{"fix_id": ...}` to prove it with a Sandbox payment.
    """
    try:
        return fix_service.run_fix(request)
    except ModuleError as error:
        status = _STATUS.get(error.code, 400)
        raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message}) from error


@router.get("/{fix_id}")
def get_fix(fix_id: str) -> dict:
    """Return an earlier fix (kept in memory until the backend restarts)."""
    result = fix_service.get_fix(fix_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "No such fix."})
    return result
