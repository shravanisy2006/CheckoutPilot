"""
Script analyzer: inspects client-side JavaScript for PayPal SDK integration
patterns (legacy v5 paypal.Buttons vs modern v6 payment sessions) and API calls.
"""

import re
from pathlib import Path

from code_agent.analyzer.models import ClientCallbackAnalysis

PAYPAL_BUTTONS_PATTERN = re.compile(r'paypal\.Buttons\s*\(', re.MULTILINE)
V6_CREATE_INSTANCE_PATTERN = re.compile(
    r'(?:window\.)?paypal\.createInstance\s*\(|createPayPalOneTimePaymentSession',
    re.MULTILINE,
)

CREATE_ORDER_ENDPOINT_PATTERN = re.compile(
    r'(?:fetch|postJson|axios\.post)\s*\(\s*["\']([^"\']*\/api\/orders)["\']',
    re.IGNORECASE,
)
CAPTURE_ENDPOINT_PATTERN = re.compile(
    r'(?:fetch|postJson|axios\.post)\s*\([^\n;]*\/api\/orders[^\n;]*capture',
    re.IGNORECASE,
)
CLIENT_TOKEN_ENDPOINT_PATTERN = re.compile(
    r'(?:fetch|getJson|axios\.get)\s*\(\s*["\']([^"\']*\/api\/paypal\/client-token)["\']',
    re.IGNORECASE,
)


def analyze_script_file(file_path: Path, repo_root: Path) -> ClientCallbackAnalysis | None:
    """Analyze a single JavaScript file for payment SDK usage."""
    rel_path = str(file_path.relative_to(repo_root)).replace("\\", "/")
    content = file_path.read_text(encoding="utf-8", errors="replace")

    uses_v5 = bool(PAYPAL_BUTTONS_PATTERN.search(content))
    uses_v6 = bool(V6_CREATE_INSTANCE_PATTERN.search(content))

    # Also detect if file calls order endpoints even if SDK itself isn't directly referenced
    create_match = CREATE_ORDER_ENDPOINT_PATTERN.search(content)
    capture_match = CAPTURE_ENDPOINT_PATTERN.search(content)
    token_match = CLIENT_TOKEN_ENDPOINT_PATTERN.search(content)

    if not (uses_v5 or uses_v6 or create_match or capture_match or token_match):
        return None

    return ClientCallbackAnalysis(
        file_path=rel_path,
        uses_paypal_buttons=uses_v5,
        uses_v6_instance=uses_v6,
        create_order_endpoint=create_match.group(1) if create_match else None,
        capture_endpoint="/api/orders/{id}/capture" if capture_match else None,
        client_token_endpoint=token_match.group(1) if token_match else None,
    )


def scan_scripts(repo_root: Path) -> list[ClientCallbackAnalysis]:
    """Scan all JavaScript files in the repository for payment logic."""
    script_files: list[Path] = []
    candidates = list(repo_root.rglob("*.js"))
    for file_path in candidates:
        parts = file_path.relative_to(repo_root).parts  # only folders inside the repo
        if any(ignored in parts for ignored in ("venv", ".venv", "node_modules", "outputs", ".git")):
            continue
        script_files.append(file_path)

    results: list[ClientCallbackAnalysis] = []
    for file_path in script_files:
        analysis = analyze_script_file(file_path, repo_root)
        if analysis:
            results.append(analysis)

    return results
