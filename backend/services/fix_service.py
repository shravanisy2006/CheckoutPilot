"""Fix service: the FIX step. POST /api/fix -> code agent writes the upgrade on a COPY of the store.

The original store is never edited: the copy goes to outputs/patched/<fix_id>/. Every fix is
registered with the verify service, so POST /api/verify {"fix_id": ...} can then make a real
PayPal Sandbox payment on the original and on the patched copy.
"""

import threading
import uuid
from typing import Any
from urllib.parse import urlparse

from backend.schemas.fix import FixRequest
from backend.schemas.models import ModuleError
from backend.services import scan_service, verify_service
from demo_stores.serve import KNOWN_STORES, resolve_store, start_store, stop_store

FIX_NO_STORE = "FIX_NO_STORE"
FIX_BUSY = "FIX_BUSY"
FIX_FAILED = "FIX_FAILED"
SCAN_NOT_FOUND = "SCAN_NOT_FOUND"
NO_ISSUES_SELECTED = "NO_ISSUES_SELECTED"
INVALID_ISSUE_IDS = "INVALID_ISSUE_IDS"
FIX_NOT_FOUND = "FIX_NOT_FOUND"
RESCAN_FAILED = "RESCAN_FAILED"

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


def create_upgrade_plan(repo_path: str, gaps: list | None = None) -> list[dict[str, Any]]:
    """Stub: code agent placeholder. Not used by run_fix() which uses build_fix() instead."""
    return []


def generate_upgrade(repo_path: str, plan: list | None = None) -> dict[str, Any]:
    """Stub: code agent placeholder. Not used by run_fix() which uses build_fix() instead."""
    return {"branch": "", "files_changed": [], "pull_request_url": ""}


def _validate_issue_ids(scan_id: str, issue_ids: list[str]) -> None:
    """Validate that issue_ids are among the scan's known issues."""
    report = scan_service.get_report(scan_id)
    if report.get("status") == "not_found":
        raise ModuleError(FIX_NO_STORE, f"No scan with id {scan_id}.")
    report_issue_ids = {i.issue_id if hasattr(i, 'issue_id') else i.get("issue_id", "") for i in report.get("issues", [])}
    invalid = [i for i in issue_ids if i not in report_issue_ids]
    if invalid:
        raise ModuleError(INVALID_ISSUE_IDS, f"Invalid issue ID(s): {', '.join(invalid)}")


def run_fix(request: FixRequest) -> dict:
    if not request.issue_ids:
        raise ModuleError(NO_ISSUES_SELECTED, "Choose at least one issue to fix.")
    if request.scan_id:
        _validate_issue_ids(request.scan_id, request.issue_ids)
    store = request.store or (_store_from_scan(request.scan_id) if request.scan_id else "legacy")
    if store not in KNOWN_STORES:
        raise ModuleError(FIX_NO_STORE, f"Unknown store {store!r}. Use one of: {', '.join(KNOWN_STORES)}.")
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
    verify_service.register_fix(fix["fix_id"], store=store, patched_store=fix["patched_store_dir"],
                                scan_id=request.scan_id)
    return fix


def get_fix(fix_id: str) -> dict | None:
    return _fixes.get(fix_id)


def rescan_fix(fix_id: str) -> dict:
    """Re-measure: scan the code agent's patched copy with the same scanner as the original.

    The copy is started on a free local port, scanned (product -> cart -> checkout, desktop and
    mobile), then stopped. The result is kept with the fix (fix["rescan"]), so the dashboard can
    compare the original store with the fixed one: health score, issues resolved, screenshots.
    """
    from pathlib import Path

    from backend.schemas.scan import ScanRequest

    fix = _fixes.get(fix_id)
    if fix is None:
        raise ModuleError(FIX_NOT_FOUND, f"No fix with id {fix_id}. Generate a fix first.")
    folder = Path(fix["patched_store_dir"])
    if not (folder / "app.py").is_file():
        raise ModuleError(FIX_NOT_FOUND, "The patched copy of this fix is no longer on disk.")
    if not _lock.acquire(blocking=False):
        raise ModuleError(FIX_BUSY, "The code agent is busy. Try again in a moment.")
    port = verify_service._free_port()
    try:
        start_store(folder, port)
        result = scan_service.run_scan(ScanRequest(store_url=f"http://localhost:{port}"))
    except Exception as error:  # store did not start, browser problem, ...
        raise ModuleError(RESCAN_FAILED, f"Could not re-scan the fixed copy: {error}") from error
    finally:
        try:
            stop_store(port)
        finally:
            _lock.release()

    rescan = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    if rescan.get("status") != "completed":
        raise ModuleError(RESCAN_FAILED, "The re-scan of the fixed copy did not complete: "
                                         + "; ".join(map(str, rescan.get("warnings") or []))[:300])
    rescan["rescan_of_fix"] = fix_id
    rescan["original_scan_id"] = fix.get("scan_id", "")
    fix["rescan"] = rescan
    return rescan

