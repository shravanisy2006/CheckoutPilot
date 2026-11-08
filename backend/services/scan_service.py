"""
Scan service: connects the API to the individual modules.

The API routes stay thin and call this service. This service calls the
modules (scanner -> ai_engine -> impact_ranker) in order. Each module only
exposes simple functions, so modules stay independent of each other.
"""

import logging

from ai_engine.checkout_analyzer import analyze_checkout
from backend.schemas.scan import Gap, ScanRequest, ScanResponse
from impact_ranker.ranker import rank_gaps
from scanner.checkout_scanner import scan_store
from scanner.exceptions import InvalidURLError, ScannerError

logger = logging.getLogger(__name__)


def run_scan(request: ScanRequest) -> ScanResponse:
    """
    Run the full audit pipeline for one store URL.

    Args:
        request: The validated scan request from the frontend.

    Returns:
        A ScanResponse containing the scan status and any ranked gaps found.
    """
    # Step 1: Validate URL and walk the store's checkout to collect raw evidence.
    try:
        scan_data = scan_store(request.store_url, include_mobile=request.include_mobile)
    except InvalidURLError as exc:
        logger.warning("Invalid URL submitted: %s — %s", request.store_url, exc)
        return ScanResponse(
            store_url=request.store_url,
            status="failed",
            message=f"Invalid store URL: {exc}",
            gaps=[],
        )
    except ScannerError as exc:
        logger.error("Scanner error for %s: %s", request.store_url, exc)
        return ScanResponse(
            store_url=request.store_url,
            status="failed",
            message=f"Scanner error: {exc}",
            gaps=[],
        )
    except Exception as exc:
        logger.exception("Unexpected error scanning %s", request.store_url)
        return ScanResponse(
            store_url=request.store_url,
            status="failed",
            message=f"Unexpected error during scan: {exc}",
            gaps=[],
        )

    # Step 2: Detect checkout gaps from the real scan data.
    try:
        gaps = analyze_checkout(scan_data)
    except Exception as exc:
        logger.error("AI engine error: %s", exc)
        gaps = []

    # Step 3: Rank the gaps by expected business impact.
    try:
        ranked_gaps = rank_gaps(gaps)
    except Exception as exc:
        logger.error("Impact ranker error: %s", exc)
        ranked_gaps = gaps

    # TODO: save the results so the reports endpoint can return them later.

    # Build a human-readable summary from real scanner output.
    scan_status = scan_data.get("status", "failed")
    sdk_version = scan_data.get("detected_sdk_version", "unknown")
    paypal_scripts = scan_data.get("paypal_scripts", [])
    errors = scan_data.get("errors", [])
    warnings = scan_data.get("warnings", [])

    if scan_status == "completed":
        message = (
            f"Scan completed. "
            f"PayPal SDK: {sdk_version}. "
            f"{len(paypal_scripts)} PayPal script(s) detected."
        )
    elif scan_status == "partial":
        warn_summary = f" Warnings: {'; '.join(warnings[:2])}" if warnings else ""
        message = (
            f"Scan partially completed. "
            f"PayPal SDK: {sdk_version}.{warn_summary}"
        )
    else:
        err_summary = f" Errors: {'; '.join(errors[:2])}" if errors else ""
        message = f"Scan failed.{err_summary}"

    return ScanResponse(
        store_url=request.store_url,
        status=scan_status,
        message=message,
        gaps=[Gap(**gap) for gap in ranked_gaps],
    )


def get_report(scan_id: str) -> dict:
    """
    Return a saved report by its ID.

    TODO: load the report from storage (e.g. SQLite) once scans are saved.
    """
    return {
        "scan_id": scan_id,
        "status": "placeholder",
        "message": "Report storage is not implemented yet.",
    }
