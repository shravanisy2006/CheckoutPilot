"""
Verify service: proves a checkout works with real PayPal Sandbox payments (PROVE step).

POST /api/verify -> run_verification() -> sandbox_verifier.verify_checkout() on the
"before" store and the "after" store -> compare_runs() -> one result dict in the
shape of docs/sample_result.json -> "verify".

Stores that are not running yet are started with demo_stores.serve.start_store and
stopped again afterwards. Only one verification runs at a time (each one drives a
browser and makes a Sandbox payment). With MOCK_VERIFIER=true no browser or PayPal
call is used.

The code agent (POST /api/fix) should call register_fix() for every fix it writes,
so that POST /api/verify {"fix_id": ...} can find the original and patched stores.
"""

import os
import socket
import threading
import time
import uuid
from pathlib import Path

import requests

from backend.schemas.models import ModuleError
from backend.schemas.verify import VerifyRequest
from backend.services.scan_service import get_report, _reports
from demo_stores.serve import KNOWN_STORES, resolve_store, start_store, stop_store
from sandbox_verifier import compare_runs, get_verifier, verify_checkout_mock

# Error codes (the API route maps them to HTTP status codes).
FIX_NOT_FOUND = "FIX_NOT_FOUND"
VERIFY_NO_TARGET = "VERIFY_NO_TARGET"
VERIFY_BAD_STORE = "VERIFY_BAD_STORE"
VERIFY_BUSY = "VERIFY_BUSY"

OUTPUTS_DIR = Path("outputs")

# fix_id -> {"store": <original store>, "patched_store": <patched store folder or URL>, "scan_id": <scan_id>}
_fixes: dict[str, dict] = {}
# verification_id -> result (in memory, like the scan reports)
_verifications: dict[str, dict] = {}
_lock = threading.Lock()


def register_fix(fix_id: str, store: str, patched_store: str, scan_id: str | None = None) -> None:
    """Called by POST /api/fix: remember which stores a fix compares.

    Args:
        fix_id: Unique fix identifier.
        store: The original (unpatched) store URL.
        patched_store: The patched store directory or URL.
        scan_id: The scan ID that originated this fix (optional).
    """
    _fixes[fix_id] = {"store": store, "patched_store": patched_store, "scan_id": scan_id}


def get_verification(verification_id: str) -> dict | None:
    return _verifications.get(verification_id)


# ----------------------------------------------------------------- helpers ---
def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _is_running(url: str) -> bool:
    try:
        return requests.get(f"{url}/health", timeout=2).status_code == 200
    except requests.RequestException:
        return False


def resolve_target(store: str) -> tuple[str, Path | None, int | None]:
    """Turn a store name, folder or URL into (url, folder to start or None, port).

    Raises ModuleError(VERIFY_BAD_STORE) for anything else.
    """
    store = (store or "").strip()
    if store.startswith(("http://", "https://")):
        return store.rstrip("/"), None, None
    if store in KNOWN_STORES:
        folder, port = resolve_store(store)
        return f"http://localhost:{port}", folder, port
    folder = Path(store)
    if folder.is_dir() and (folder / "app.py").is_file():
        port = _free_port()
        return f"http://localhost:{port}", folder.resolve(), port
    raise ModuleError(VERIFY_BAD_STORE,
                      f"Unknown store {store!r}. Use 'legacy', 'upgraded', a store folder or a local URL.")


def to_file_url(path: str) -> str:
    """outputs/verifications/x/01.png -> /files/verifications/x/01.png (served by the backend)."""
    path = str(path).replace("\\", "/")
    marker = "outputs/"
    if marker in path:
        return "/files/" + path.split(marker, 1)[1]
    return path


def _verify_one(store: str, label: str, page: str, verifier, mock: bool) -> dict:
    """Start the store if needed, run one Sandbox purchase, stop the store again."""
    url, folder, port = resolve_target(store)
    started = None
    if not mock and folder is not None and not _is_running(url):
        start_store(folder, port)
        started = port
    try:
        if mock:
            result = verifier(url, label=label)
        else:
            # VERIFY_HEADLESS=false in .env shows the browser (useful for demos and debugging).
            headless = os.getenv("VERIFY_HEADLESS", "true").strip().lower() not in ("0", "false", "no")
            result = verifier(url, label=label, page=page, headless=headless)
    finally:
        if started is not None:
            stop_store(started)
    result = dict(result)
    result["screenshots"] = [to_file_url(p) for p in result.get("screenshots", [])]
    result["is_real_sandbox_payment"] = not mock and bool(result.get("api_confirmed"))
    return result


# ------------------------------------------------------------ main entry ---
def run_verification(request: VerifyRequest) -> dict:
    """Make the Sandbox payments and compare them. Takes about 1-2 minutes for two stores."""
    if request.fix_id:
        fix = _fixes.get(request.fix_id)
        if fix is None:
            raise ModuleError(FIX_NOT_FOUND,
                              f"No fix with id {request.fix_id!r}. POST /api/fix must create it first "
                              "(or send before_store / after_store instead).")
        before_store, after_store = fix["store"], fix["patched_store"]
    elif request.after_store:
        before_store, after_store = request.before_store, request.after_store
    else:
        raise ModuleError(VERIFY_NO_TARGET,
                          "Send fix_id, or after_store (and optionally before_store), e.g. "
                          '{"before_store": "legacy", "after_store": "upgraded"}.')

    # Check the store names before taking the lock, so mistakes fail fast.
    for store in (before_store, after_store):
        if store:
            resolve_target(store)

    if not _lock.acquire(blocking=False):
        raise ModuleError(VERIFY_BUSY, "Another Sandbox verification is running. Try again in a minute.")
    try:
        verifier = get_verifier()
        mock = verifier is verify_checkout_mock
        before = _verify_one(before_store, "before", request.page, verifier, mock) if before_store else None
        after = _verify_one(after_store, "after", request.page, verifier, mock)
    finally:
        _lock.release()

    if before is not None:
        comparison = compare_runs(before, after)
    else:
        comparison = {
            "before": None,
            "after": after,
            "safe_to_approve": bool(after.get("purchase_succeeded")),
            "summary": "Checkout works." if after.get("purchase_succeeded")
            else "The checkout did not complete a Sandbox payment.",
            "changes": [],
        }

    verification_id = f"verify_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    result = {
        "verification_id": verification_id,
        "fix_id": request.fix_id,
        "before": comparison["before"],
        "after": comparison["after"],
        "safe_to_approve": comparison["safe_to_approve"],
        "summary": comparison["summary"],
        "changes": comparison["changes"],
        "simulated": mock,
    }
    _verifications[verification_id] = result

    # Store the verification result in the originating scan report, if applicable.
    if request.fix_id:
        fix = _fixes.get(request.fix_id)
        scan_id = fix.get("scan_id") if fix else None
        if scan_id and scan_id in _reports:
            _reports[scan_id]["verification"] = result

    return result
