"""
Repository Analyzer: coordinates template, script, route, and layout inspection
to produce a complete PaymentContext for the store repository.
"""

from pathlib import Path
from typing import Any, Optional

from code_agent.analyzer.css_analyzer import scan_css
from code_agent.analyzer.models import PaymentContext
from code_agent.analyzer.route_analyzer import scan_routes
from code_agent.analyzer.script_analyzer import scan_scripts
from code_agent.analyzer.template_analyzer import scan_templates


def analyze_repository(
    repo_path: str | Path,
    scan_data: Optional[dict[str, Any]] = None,
    gaps: Optional[list[dict[str, Any]]] = None,
) -> PaymentContext:
    """
    Analyze a store repository for all payment-related code and configurations.

    Args:
        repo_path: Local path to the store's code repository.
        scan_data: Optional outside-in scan dictionary from scanner.
        gaps: Optional list of identified checkout gaps.

    Returns:
        PaymentContext instance containing all detected payment artifacts.
    """
    root = Path(repo_path).resolve()
    if not root.exists() or not root.is_dir():
        ctx = PaymentContext(repo_path=str(repo_path))
        ctx.warnings.append(f"Repository path does not exist: {repo_path}")
        return ctx

    # 1. Run deterministic scanners
    sdk_refs, button_containers, missing_pages, layout = scan_templates(root)
    client_callbacks = scan_scripts(root)
    server_endpoints = scan_routes(root)
    css_reports = scan_css(root)

    # 2. Correlate CSS layout with template layout
    if layout and css_reports:
        # Check if style.css defines the reordering or standard order
        for report in css_reports:
            if report.get("has_checkout_styling"):
                layout.style_file = report["file_path"]
                if report.get("has_responsive_reordering"):
                    layout.button_below_form_on_mobile = False

    # 3. Determine overall detected SDK version
    detected_version = "missing"
    if any(ref.version == "v6" for ref in sdk_refs) or any(cb.uses_v6_instance for cb in client_callbacks):
        detected_version = "v6"
    elif any(ref.version == "v5" for ref in sdk_refs) or any(cb.uses_paypal_buttons for cb in client_callbacks):
        detected_version = "v5"

    # 4. Check backend endpoints
    has_client_token = any(ep.endpoint_type == "client_token" for ep in server_endpoints)
    has_create_order = any(ep.endpoint_type == "create_order" for ep in server_endpoints)
    has_capture_order = any(ep.endpoint_type == "capture_order" for ep in server_endpoints)

    # 5. Guided correlation with scan_data / gaps if provided
    guided_list = list(gaps) if gaps else []
    if scan_data and not guided_list:
        # Check if scan_data has warnings or sdk version
        if scan_data.get("paypal_sdk_version") and detected_version == "missing":
            detected_version = scan_data["paypal_sdk_version"]

    context = PaymentContext(
        repo_path=str(root),
        sdk_references=sdk_refs,
        button_containers=button_containers,
        missing_button_pages=missing_pages,
        client_callbacks=client_callbacks,
        server_endpoints=server_endpoints,
        layout=layout,
        detected_sdk_version=detected_version,
        has_client_token_route=has_client_token,
        has_create_order_route=has_create_order,
        has_capture_order_route=has_capture_order,
        guided_gaps=guided_list,
    )

    return context
