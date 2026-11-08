"""
Scan service: connects the API to the individual modules.

The API routes stay thin and call this service. This service calls the
modules (scanner -> ai_engine -> impact_ranker) in order. Each module only
exposes simple functions, so modules stay independent of each other.

Reports are stored in a module-level in-memory dictionary keyed by scan_id.
This storage is:
  - In-memory only (no database or file persistence).
  - Per-process (each Uvicorn worker has its own copy).
  - Lost when the application restarts.
This is acceptable for the current hackathon MVP.
"""

import logging
import uuid

from ai_engine.checkout_analyzer import analyze_checkout_detailed

logger = logging.getLogger(__name__)
from backend.schemas.models import ModuleError
from backend.schemas.scan import Gap, ScanRequest, ScanResponse
from impact_ranker.ranker import health_score, rank_issues
from scanner.checkout_scanner import scan_store
from scanner.exceptions import InvalidURLError

# In-memory report storage keyed by scan_id (demo scope).
# See module docstring for persistence and thread-safety limitations.
_reports: dict[str, dict] = {}


def _build_failed_record(
    scan_id: str,
    store_url: str,
    message: str,
    warnings: list[str],
) -> dict:
    """Build a consistent failed-scan record without exposing internals."""
    return {
        "scan_id": scan_id,
        "store_url": store_url,
        "status": "failed",
        "message": message,
        "gaps": [],
        "health_score": None,
        "warnings": warnings,
    }


def run_scan(request: ScanRequest) -> ScanResponse:
    """
    Run the full audit pipeline for one store URL.

    Args:
        request: The validated scan request from the frontend.

    Returns:
        A ScanResponse containing the ranked gaps found, or a failed
        response when the scanner yields malformed/no page data or a
        module raises. Internal exception details and secrets are never
        exposed in the response.
    """
    scan_id = str(uuid.uuid4())

    try:
        # Step 1: walk the store's checkout and collect raw data.
        scan_data = scan_store(request.store_url, include_mobile=request.include_mobile)

        # Validate scanner output explicitly.
        if not isinstance(scan_data, dict):
            warning = (
                "The scanner returned malformed output (expected a dictionary, "
                f"got {type(scan_data).__name__}). No checkout page data was "
                "collected."
            )
            record = _build_failed_record(
                scan_id, request.store_url,
                "Scan could not collect any checkout page data.",
                [warning],
            )
            _reports[scan_id] = record
            return ScanResponse(**record)

        pages = scan_data.get("pages")
        if not isinstance(pages, list) or len(pages) == 0:
            warning = (
                "No checkout page data was collected. The scanner returned no "
                "pages, so a health score cannot be reported reliably."
            )
            record = _build_failed_record(
                scan_id, request.store_url,
                "Scan could not collect any checkout page data.",
                [warning],
            )
            _reports[scan_id] = record
            return ScanResponse(**record)

        # Step 2: detect checkout gaps from the raw data using detailed analysis.
        # This returns {"issues": [...], "warnings": [...]} explicitly, with no
        # reliance on side-effect mutation of scan_data.
        analysis = analyze_checkout_detailed(scan_data)
        issues = analysis.get("issues", [])
        warnings = analysis.get("warnings", [])

        # Step 3: rank the gaps by expected business impact.
        ranked_gaps = rank_issues(issues)

        # Step 4: calculate health score (only when pages were collected).
        computed_health_score = health_score(ranked_gaps)

        # Step 5: map ranked issues into the Gap schema, preserving all useful
        # issue information additively. description and evidence are kept
        # separate; raw evidence is never copied into description.
        gap_models = []
        for item in ranked_gaps:
            impact = item.get("impact", {}) or {}
            score = impact.get("score", 0)
            assumption = impact.get("assumption", "")
            estimated = f"Score {score}/100 - {assumption}".strip(" -")
            gap_models.append(
                Gap(
                    gap_id=item.get("issue_id", "unknown"),
                    title=item.get("title", ""),
                    severity=item.get("severity", "unknown"),
                    description=item.get("description", ""),
                    estimated_impact=estimated,
                    impact=impact,
                    evidence=item.get("evidence", ""),
                    category=item.get("category", ""),
                    confidence=item.get("confidence", 1.0),
                    screenshot_path=item.get("screenshot_path", ""),
                    fixable_by_agent=item.get("fixable_by_agent", False),
                )
            )

        message = (
            f"Scan completed. Found {len(gap_models)} issue(s). "
            f"Health score: {computed_health_score}/100."
        )

        record = {
            "scan_id": scan_id,
            "store_url": request.store_url,
            "status": "completed",
            "message": message,
            "gaps": [g.model_dump() for g in gap_models],
            "health_score": computed_health_score,
            "warnings": warnings,
        }
        _reports[scan_id] = record
        return ScanResponse(**record)

    except InvalidURLError as error:
        # Invalid store URL: return a clear failure response without exposing
        # stack traces or internal details.
        message = f"Invalid store URL: {str(error)}."
        record = _build_failed_record(scan_id, request.store_url, message, [])
        _reports[scan_id] = record
        return ScanResponse(**record)

    except ModuleError as error:
        # Module errors: return a safe failure response; never expose stack
        # traces or secrets to the caller.
        message = f"Scan failed: {error.code} - {error.message}."
        record = _build_failed_record(scan_id, request.store_url, message, [])
        _reports[scan_id] = record
        return ScanResponse(**record)

    except Exception:
        # Unexpected exceptions: generic safe message, no secret or stack
        # trace exposure. Log the full exception internally for debugging.
        logger.exception("Unexpected error during scan %s", scan_id)
        message = "Scan failed due to an unexpected error."
        record = _build_failed_record(scan_id, request.store_url, message, [])
        _reports[scan_id] = record
        return ScanResponse(**record)


def get_report(scan_id: str) -> dict:
    """
    Return a saved report by its ID.

    Args:
        scan_id: The scan ID returned by run_scan.

    Returns:
        The stored scan record, or a not-found dictionary with
        ``status == "not_found"``. The API route translates this to HTTP 404.
    """
    record = _reports.get(scan_id)
    if record is None:
        return {
            "scan_id": scan_id,
            "status": "not_found",
            "message": "No report found for this scan ID.",
        }
    return record
