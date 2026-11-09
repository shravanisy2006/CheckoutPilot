"""Scan service: connects the API to the individual modules.

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
import os
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from ai_engine.checkout_analyzer import analyze_checkout_detailed
from backend.schemas.models import ModuleError
from backend.schemas.scan import Gap, Impact, ScanRequest, ScanResponse
from impact_ranker.ranker import health_score, rank_issues
from scanner.browser import BrowserConfig
from scanner.checkout_scanner import scan_store
from scanner.exceptions import InvalidURLError

logger = logging.getLogger(__name__)

# In-memory report storage keyed by scan_id (demo scope).
# See module docstring for persistence and thread-safety limitations.
_reports: dict[str, dict] = {}


def _scan_id() -> str:
    """Generate a timestamped scan ID, e.g. scan_20261108_132000_ab12."""
    now = datetime.now(tz=timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:4]
    return f"scan_{ts}_{suffix}"


def _health_label(score: int | None) -> str:
    """Convert a health score (0-100) to a label."""
    if score is None:
        return ""
    if score < 50:
        return "poor"
    if score < 80:
        return "fair"
    return "good"


def _issue_counts(ranked_issues: list[dict]) -> dict[str, int]:
    """Count issues by severity."""
    counts = {"high": 0, "medium": 0, "low": 0}
    for item in ranked_issues:
        sev = item.get("severity", "unknown")
        if sev in counts:
            counts[sev] += 1
    return counts


def _map_page_to_contract(page: dict, scan_id: str) -> dict:
    """Map a scanner page dict to the API contract page format."""
    screenshot_path = page.get("screenshot_path", "") or ""
    screenshot_url = ""
    if screenshot_path:
        basename = os.path.basename(screenshot_path)
        screenshot_url = f"/files/scans/{scan_id}/{basename}"

    paypal_elements = page.get("paypal_elements") or []
    paypal_found = any(el.get("visible", False) for el in paypal_elements)

    # Check if any visible PayPal element is above the fold.
    viewport_height = page.get("viewport_height")
    paypal_visible_without_scroll = False
    for el in paypal_elements:
        if not el.get("visible", False):
            continue
        box = el.get("bounding_box") or {}
        y = box.get("y", 0)
        height = box.get("height", 0)
        bottom = y + height
        if viewport_height is not None:
            if 0 < bottom <= viewport_height:
                paypal_visible_without_scroll = True
                break
        else:
            # Fall back to default viewport heights.
            default_heights = {"desktop": 800, "mobile": 667}
            vp_height = default_heights.get(page.get("viewport", "desktop"), 800)
            if 0 < bottom <= vp_height:
                paypal_visible_without_scroll = True
                break

    return {
        "step": page.get("step", ""),
        "viewport": page.get("viewport", ""),
        "url": page.get("url", ""),
        "screenshot_url": screenshot_url,
        "paypal_found": paypal_found,
        "paypal_visible_without_scroll": paypal_visible_without_scroll,
    }


def _map_issue_to_contract(item: dict, scan_id: str) -> Gap:
    """Map a ranked issue dict to the contract Gap model."""
    impact = item.get("impact", {}) or {}
    screenshot_path = item.get("screenshot_path", "") or ""
    screenshot_url = ""
    if screenshot_path:
        basename = os.path.basename(screenshot_path)
        screenshot_url = f"/files/scans/{scan_id}/{basename}"

    return Gap(
        issue_id=item.get("issue_id", "unknown"),
        title=item.get("title", ""),
        category=item.get("category", "unknown"),
        severity=item.get("severity", "unknown"),
        source=item.get("source", "rule"),
        confidence=float(item.get("confidence", 1.0) or 1.0),
        evidence=item.get("evidence", ""),
        screenshot_url=screenshot_url,
        fixable_by_agent=bool(item.get("fixable_by_agent", False)),
        description=item.get("description", ""),
        impact=Impact(
            issue_id=item.get("issue_id", "unknown"),
            score=int(impact.get("score", 0)),
            rank=int(impact.get("rank", 0)),
            rationale=impact.get("rationale", ""),
            assumption=impact.get("assumption", ""),
            assumption_source=impact.get("assumption_source", ""),
        ),
    )


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
        "scanned_at": datetime.now(tz=timezone.utc).isoformat(),
        "status": "failed",
        "message": message,
        "issues": [],
        "health_score": None,
        "health_label": "",
        "issue_counts": {"high": 0, "medium": 0, "low": 0},
        "paypal_sdk_version": "none",
        "pages": [],
        "warnings": warnings,
        "fix": None,
        "verification": None,
    }


def run_scan(request: ScanRequest) -> ScanResponse:
    """Run the full audit pipeline for one store URL.

    Args:
        request: The validated scan request from the frontend.

    Returns:
        A ScanResponse containing the ranked gaps found, or a failed
        response when the scanner yields malformed/no page data or a
        module raises. Internal exception details and secrets are never
        exposed in the response.
    """
    scan_id = _scan_id()

    try:
        # Step 1: walk the store's checkout and collect raw data.
        # Save screenshots under outputs/scans/<scan_id>/, which the backend serves at /files/scans/...
        # (the page and issue screenshot_url values below point there).
        config = replace(BrowserConfig.from_env(), screenshots_dir=str(Path("outputs") / "scans" / scan_id))
        scan_data = scan_store(request.store_url, include_mobile=request.include_mobile, config=config)

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
        # issue information additively.
        gap_models = []
        for item in ranked_gaps:
            gap_models.append(_map_issue_to_contract(item, scan_id))

        # Step 6: map scanner pages to contract page format.
        contract_pages = [_map_page_to_contract(page, scan_id) for page in pages]

        # Step 7: compute derived fields.
        computed_health_score = health_score(ranked_gaps)
        computed_label = _health_label(computed_health_score)
        counts = _issue_counts(ranked_gaps)
        detected_sdk = scan_data.get("detected_sdk_version", "none") or "none"
        if detected_sdk == "unknown":
            detected_sdk = "none"

        # Pass through scanner's status ("completed", "partial", or "failed").
        scan_status = scan_data.get("status", "completed")
        if scan_status not in ("completed", "partial", "failed"):
            scan_status = "completed"

        message = (
            f"Scan completed. Found {len(gap_models)} issue(s). "
            f"Health score: {computed_health_score}/100."
        )

        record = {
            "scan_id": scan_id,
            "store_url": request.store_url,
            "scanned_at": datetime.now(tz=timezone.utc).isoformat(),
            "status": scan_status,
            "message": message,
            "paypal_sdk_version": detected_sdk,
            "health_score": computed_health_score,
            "health_label": computed_label,
            "issue_counts": counts,
            "issues": [g.model_dump() for g in gap_models],
            "pages": contract_pages,
            "warnings": warnings,
            "fix": None,
            "verification": None,
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
    """Return a saved report by its ID.

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