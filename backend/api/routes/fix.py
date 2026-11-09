"""Fix routes: write PayPal checkout upgrades (FIX step)."""

from fastapi import APIRouter, HTTPException

from backend.schemas.fix import FixRequest, FixResponse
from backend.services import fix_service
from backend.schemas.models import ModuleError

router = APIRouter(prefix="/fix", tags=["Fix"])

_STATUS = {
    fix_service.SCAN_NOT_FOUND: 404,
    fix_service.NO_ISSUES_SELECTED: 400,
    fix_service.INVALID_ISSUE_IDS: 400,
    fix_service.CODE_AGENT_NOT_READY: 503,
}


@router.post("")
def fix(request: FixRequest) -> FixResponse:
    """Write PayPal checkout upgrades for a scanned store.

    Example body: `{"scan_id": "scan_demo_legacy",
    "issue_ids": ["sdk_outdated", "no_paypal_on_cart"]}`.
    Errors: `{"detail": {"code": "...", "message": "..."}}`.
    """
    try:
        return fix_service.run_fix(request)
    except ModuleError as error:
        status = _STATUS.get(error.code, 400)
        raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message}) from error
