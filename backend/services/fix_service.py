"""
Fix service: the FIX step. POST /api/fix -> code agent writes the upgrade on a COPY of the store.

The original store is never edited: the copy goes to outputs/patched/<fix_id>/. Every fix is
registered with the verify service, so POST /api/verify {"fix_id": ...} can then make a real
PayPal Sandbox payment on the original and on the patched copy.
"""

import threading
import uuid
from urllib.parse import urlparse

from backend.schemas.fix import FixRequest
from backend.schemas.models import ModuleError
from backend.services import scan_service, verify_service
from demo_stores.serve import KNOWN_STORES, resolve_store

FIX_NO_STORE = "FIX_NO_STORE"
FIX_BUSY = "FIX_BUSY"
FIX_FAILED = "FIX_FAILED"

_fixes: dict[str, dict] = {}
_lock = threading.Lock()


def _store_from_scan(scan_id: str) -> str:
    report = scan_service.get_report(scan_id)
    if report.get("status") == "not_found":
        raise ModuleError(FIX_NO_STORE, f"No scan with id {scan_id}. Run a scan first, or send \"store\".")
    url = urlparse(report.get("store_url", ""))
    for name, (_, port) in KNOWN_STORES.items():
        if url.hostname in ("localhost", "127.0.0.1") and url.port == port:
            return name
    raise ModuleError(FIX_NO_STORE, "The code agent can only patch stores whose code we have (the demo "
                                    "stores). For a real store it would work on the merchant's repository.")


def run_fix(request: FixRequest) -> dict:
    store = request.store or (_store_from_scan(request.scan_id) if request.scan_id else "legacy")
    if store not in KNOWN_STORES:
        raise ModuleError(FIX_NO_STORE, f"Unknown store {store!r}. Use one of: {', '.join(KNOWN_STORES)}.")
    if not request.issue_ids:
        raise ModuleError(FIX_NO_STORE, "Choose at least one issue to fix.")
    if not _lock.acquire(blocking=False):
        raise ModuleError(FIX_BUSY, "A fix is already being written. Try again in a moment.")
    try:
        from code_agent.fix_builder import build_fix

        folder, _ = resolve_store(store)
        fix = build_fix(folder, request.issue_ids, fix_id=f"fix_{uuid.uuid4().hex[:10]}",
                        scan_id=request.scan_id or "")
    except (OSError, ValueError) as error:
        raise ModuleError(FIX_FAILED, f"The code agent could not write the fix: {error}") from error
    finally:
        _lock.release()

    _fixes[fix["fix_id"]] = fix
    if fix["status"] != "proposed":
        problems = "; ".join(fix["errors"]) or "no files were changed"
        raise ModuleError(FIX_FAILED, f"The upgrade did not pass its checks ({problems}). "
                                      f"Details: GET /api/fix/{fix['fix_id']}")
    verify_service.register_fix(fix["fix_id"], store=store, patched_store=fix["patched_store_dir"])
    return fix


def get_fix(fix_id: str) -> dict | None:
    return _fixes.get(fix_id)
