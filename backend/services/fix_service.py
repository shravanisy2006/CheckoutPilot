"""Fix service: connects the backend API to the code agent module (FIX step).

POST /api/fix -> run_fix() -> code_agent.create_upgrade_plan() ->
code_agent.generate_upgrade() -> fix result stored in the scan report.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.schemas.fix import FixRequest, FixResponse
from backend.schemas.models import ModuleError
from backend.services.scan_service import get_report
from backend.services.verify_service import register_fix
from code_agent.upgrade_agent import create_upgrade_plan, generate_upgrade

# Error codes (the API route maps them to HTTP status codes).
SCAN_NOT_FOUND = "SCAN_NOT_FOUND"
NO_ISSUES_SELECTED = "NO_ISSUES_SELECTED"
INVALID_ISSUE_IDS = "INVALID_ISSUE_IDS"
CODE_AGENT_NOT_READY = "CODE_AGENT_NOT_READY"
STORE_NOT_SUPPORTED = "STORE_NOT_SUPPORTED"

# Mapping from store URLs scanned by the backend to their local repository
# directories.  The code agent needs a filesystem path, not an HTTP URL.
STORE_URL_TO_REPO_PATH: dict[str, Path] = {
    "http://localhost:8101": Path("demo_stores/legacy_store").resolve(),
    "http://localhost:8102": Path("demo_stores/upgraded_store").resolve(),
}

# fix_id -> {"store": str, "patched_store": str, "scan_id": str}
_fixes: dict[str, dict] = {}


def _fix_id() -> str:
    """Generate a fix ID, e.g. fix_20261108_132000_ab12."""
    now = datetime.now(tz=timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:4]
    return f"fix_{ts}_{suffix}"


def resolve_repo_path(store_url: str) -> Path:
    """Resolve a store URL to its local repository directory.

    Args:
        store_url: The store URL as scanned (e.g. "http://localhost:8101").

    Returns:
        A Path to the local demo store directory.

    Raises:
        ModuleError: STORE_NOT_SUPPORTED if the URL is not mapped or the
            directory does not exist.
    """
    repo_path = STORE_URL_TO_REPO_PATH.get(store_url)
    if repo_path is None:
        raise ModuleError(STORE_NOT_SUPPORTED, f"Store URL not supported: {store_url}")
    if not repo_path.is_dir() or not (repo_path / "app.py").is_file():
        raise ModuleError(
            STORE_NOT_SUPPORTED,
            f"Store repository not found or missing app.py: {repo_path}",
        )
    return repo_path


def run_fix(request: FixRequest) -> FixResponse:
    """Run the fix pipeline for one store scan.

    Args:
        request: The validated fix request from the frontend.

    Returns:
        A FixResponse containing the fix result, or raises ModuleError
        if the scan is not found, no issues are selected, the issue IDs
        are invalid, the store URL is unsupported, or the code agent
        is not ready.

    Raises:
        ModuleError: If the scan is not found, no issues are selected,
            invalid issue IDs are provided, the store URL is unsupported,
            the patched store directory does not exist, or the code agent
            is not ready.
    """
    # Step 1: Get the scan report.
    scan_report = get_report(request.scan_id)
    if scan_report.get("status") == "not_found":
        raise ModuleError(SCAN_NOT_FOUND, f"No scan with id {request.scan_id}")

    # Step 2: Validate that issue_ids exist in the scan.
    scan_issues = scan_report.get("issues", [])
    scan_issue_ids = {issue["issue_id"] for issue in scan_issues}
    requested_ids = set(request.issue_ids)
    if not requested_ids:
        raise ModuleError(NO_ISSUES_SELECTED, "No issue_ids provided")
    if not requested_ids.issubset(scan_issue_ids):
        invalid = requested_ids - scan_issue_ids
        raise ModuleError(INVALID_ISSUE_IDS, f"Unknown issue_id(s): {invalid}")

    # Step 3: Get selected issues for the code agent.
    selected_issues = [i for i in scan_issues if i["issue_id"] in requested_ids]

    # Step 4: Resolve the store URL to a local repository path.
    repo_path = resolve_repo_path(scan_report.get("store_url", ""))

    # Step 5: Call the code agent to create an upgrade plan.
    plan = create_upgrade_plan(str(repo_path), selected_issues)
    if not plan:
        raise ModuleError(CODE_AGENT_NOT_READY, "Code agent did not produce an upgrade plan")

    # Step 6: Call the code agent to generate the upgrade.
    result = generate_upgrade(str(repo_path), plan)
    if not result.get("files_changed") or not result.get("branch"):
        raise ModuleError(CODE_AGENT_NOT_READY, "Code agent did not produce a valid upgrade")

    # Step 7: Generate a fix ID and validate the patched store directory exists.
    fix_id = _fix_id()
    patched_store_dir = f"outputs/patched/{fix_id}"
    patched_path = Path(patched_store_dir)
    if not patched_path.is_dir() or not (patched_path / "app.py").is_file():
        raise ModuleError(
            CODE_AGENT_NOT_READY,
            "Patched store directory does not exist or is incomplete",
        )

    # Step 8: Register the fix with scan_id.
    register_fix(fix_id, scan_report["store_url"], patched_store_dir, request.scan_id)

    # Step 9: Store the fix result in the scan report.
    scan_report["fix"] = {
        "fix_id": fix_id,
        "scan_id": request.scan_id,
        "status": "proposed",
        "issue_ids": list(request.issue_ids),
        "summary": result.get("summary", ""),
        "explanation": result.get("explanation", []),
        "files": result.get("files", []),
        "branch": result.get("branch", ""),
        "pr_url": result.get("pr_url", ""),
        "patched_store_dir": patched_store_dir,
    }

    # Step 10: Return the FixResponse.
    return FixResponse(
        fix_id=fix_id,
        scan_id=request.scan_id,
        status="proposed",
        issue_ids=list(request.issue_ids),
        summary=result.get("summary", ""),
        explanation=result.get("explanation", []),
        files=result.get("files", []),
        branch=result.get("branch", ""),
        pr_url=result.get("pr_url", ""),
        patched_store_dir=patched_store_dir,
    )