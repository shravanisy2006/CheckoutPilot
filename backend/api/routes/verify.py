"""Verify routes: prove a checkout works with real PayPal Sandbox payments (PROVE step)."""

from fastapi import APIRouter, HTTPException

from backend.schemas.models import ModuleError
from backend.schemas.verify import VerifyRequest
from backend.services import verify_service

router = APIRouter(prefix="/verify", tags=["Verify"])

_STATUS = {
    verify_service.FIX_NOT_FOUND: 404,
    verify_service.VERIFY_BUSY: 409,
}


@router.post("")
def verify(request: VerifyRequest) -> dict:
    """Make a real PayPal Sandbox test purchase on the "before" and "after" stores and compare them.

    Example body (works today): `{"before_store": "legacy", "after_store": "upgraded"}`.
    Takes about 1-2 minutes. Response shape: docs/sample_result.json -> "verify".
    Errors: `{"detail": {"code": "...", "message": "..."}}`.
    """
    try:
        return verify_service.run_verification(request)
    except ModuleError as error:
        status = _STATUS.get(error.code, 400)
        raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message}) from error


@router.get("/{verification_id}")
def get_verification(verification_id: str) -> dict:
    """Return an earlier verification result (kept in memory until the backend restarts)."""
    result = verify_service.get_verification(verification_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "No such verification."})
    return result
