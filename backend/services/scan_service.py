"""
Scan service: connects the API to the individual modules.

The API routes stay thin and call this service. This service calls the
modules (scanner -> ai_engine -> impact_ranker) in order. Each module only
exposes simple functions, so modules stay independent of each other.

Right now every module returns placeholder data, so this pipeline runs end
to end without doing any real work.
"""

from ai_engine.checkout_analyzer import analyze_checkout
from backend.schemas.scan import Gap, ScanRequest, ScanResponse
from impact_ranker.ranker import rank_gaps
from scanner.checkout_scanner import scan_store


def run_scan(request: ScanRequest) -> ScanResponse:
    """
    Run the full audit pipeline for one store URL.

    Args:
        request: The validated scan request from the frontend.

    Returns:
        A ScanResponse containing the ranked gaps found.
    """
    # Step 1: walk the store's checkout and collect raw data.
    scan_data = scan_store(request.store_url, include_mobile=request.include_mobile)

    # Step 2: detect checkout gaps from the raw data.
    gaps = analyze_checkout(scan_data)

    # Step 3: rank the gaps by expected business impact.
    ranked_gaps = rank_gaps(gaps)

    # TODO: save the results so the reports endpoint can return them later.

    return ScanResponse(
        store_url=request.store_url,
        status="placeholder",
        message="Scan pipeline is wired up. Real scanning is not implemented yet.",
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
