"""
Template analyzer: inspects HTML and Jinja templates for PayPal SDK inclusions,
button containers, and presentment gaps across cart and checkout pages.
"""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from code_agent.analyzer.models import ButtonContainer, LayoutAnalysis, SdkReference

V5_SDK_PATTERN = re.compile(
    r'<script[^>]+src=["\']([^"\']*paypal\.com/sdk/js[^"\']*)["\'][^>]*>',
    re.IGNORECASE,
)
V6_SDK_PATTERN = re.compile(
    r'<script[^>]+src=["\']([^"\']*(?:paypal\.com/web-sdk/v6|PAYPAL_SDK_URL)[^"\']*)["\'][^>]*>',
    re.IGNORECASE,
)
CUSTOM_BUTTON_PATTERN = re.compile(
    r'<paypal-button\b([^>]*)>',
    re.IGNORECASE,
)
CONTAINER_PATTERN = re.compile(
    r'id=["\'](paypal-button-container|paypal-button|cart-paypal-button)["\']',
    re.IGNORECASE,
)


def _guess_page_type(file_path: Path, content: str) -> str:
    """Determine whether the template represents a checkout, cart, or product page."""
    stem = file_path.stem.lower()
    if "checkout" in stem:
        return "checkout"
    if "cart" in stem:
        return "cart"
    if "product" in stem or "item" in stem:
        return "product"

    match = re.search(r'data-page=["\']([^"\']+)["\']', content, re.IGNORECASE)
    if match:
        page = match.group(1).lower()
        if "checkout" in page:
            return "checkout"
        if "cart" in page:
            return "cart"
        if "product" in page:
            return "product"

    return "unknown"


def analyze_template_file(
    file_path: Path,
    repo_root: Path,
) -> tuple[list[SdkReference], list[ButtonContainer], Optional[LayoutAnalysis]]:
    """
    Analyze a single HTML/Jinja template file.

    Returns:
        (sdk_references, button_containers, optional_layout)
    """
    rel_path = str(file_path.relative_to(repo_root)).replace("\\", "/")
    content = file_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()

    sdk_refs: list[SdkReference] = []
    button_containers: list[ButtonContainer] = []
    layout: Optional[LayoutAnalysis] = None

    page_type = _guess_page_type(file_path, content)

    # 1. Scan for SDK script references
    for idx, line in enumerate(lines, start=1):
        v5_match = V5_SDK_PATTERN.search(line)
        if v5_match:
            raw_url = v5_match.group(1)
            parsed = urlparse(raw_url)
            query_params = parse_qs(parsed.query)

            sdk_refs.append(
                SdkReference(
                    file_path=rel_path,
                    line_number=idx,
                    raw_tag=line.strip(),
                    version="v5",
                    client_id_param=query_params.get("client-id", [None])[0],
                    components_param=query_params.get("components", [None])[0],
                    currency_param=query_params.get("currency", [None])[0],
                    is_v6=False,
                )
            )
            continue

        v6_match = V6_SDK_PATTERN.search(line)
        if v6_match:
            sdk_refs.append(
                SdkReference(
                    file_path=rel_path,
                    line_number=idx,
                    raw_tag=line.strip(),
                    version="v6",
                    is_v6=True,
                )
            )

    # 2. Scan for button containers or custom elements
    for idx, line in enumerate(lines, start=1):
        custom_match = CUSTOM_BUTTON_PATTERN.search(line)
        if custom_match:
            attrs = custom_match.group(1)
            id_match = re.search(r'id=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            elem_id = id_match.group(1) if id_match else "paypal-button"
            button_containers.append(
                ButtonContainer(
                    file_path=rel_path,
                    line_number=idx,
                    element_id=elem_id,
                    element_type="custom_element",
                    page_type=page_type,
                )
            )
            continue

        container_match = CONTAINER_PATTERN.search(line)
        if container_match:
            button_containers.append(
                ButtonContainer(
                    file_path=rel_path,
                    line_number=idx,
                    element_id=container_match.group(1),
                    element_type="container",
                    page_type=page_type,
                )
            )

    # 3. If checkout page, check DOM element ordering for mobile below-the-fold layout
    if page_type == "checkout":
        form_line = None
        summary_line = None
        for idx, line in enumerate(lines, start=1):
            if re.search(r'<form\b[^>]*id=["\']shipping-form["\']', line, re.IGNORECASE):
                form_line = idx
            elif re.search(r'<aside\b[^>]*id=["\']order-summary["\']', line, re.IGNORECASE):
                summary_line = idx

        if form_line is not None and summary_line is not None:
            # If the form precedes the summary/button, on single-column mobile viewports
            # the button will be placed below the long input form
            layout = LayoutAnalysis(
                template_file=rel_path,
                button_below_form_on_mobile=(form_line < summary_line),
                shipping_form_line=form_line,
                summary_container_line=summary_line,
            )

    return sdk_refs, button_containers, layout


def scan_templates(
    repo_root: Path,
) -> tuple[list[SdkReference], list[ButtonContainer], list[str], Optional[LayoutAnalysis]]:
    """
    Scan all template files in a repository.

    Returns:
        (all_sdk_refs, all_button_containers, missing_button_pages, checkout_layout)
    """
    template_files: list[Path] = []
    # Search common template directories or root HTML files
    candidates = list(repo_root.rglob("*.html"))
    for file_path in candidates:
        parts = file_path.parts
        # Skip virtualenvs or node_modules or outputs
        if any(ignored in parts for ignored in ("venv", ".venv", "node_modules", "outputs", ".git")):
            continue
        template_files.append(file_path)

    all_sdk_refs: list[SdkReference] = []
    all_button_containers: list[ButtonContainer] = []
    layout: Optional[LayoutAnalysis] = None
    pages_with_buttons: set[str] = set()
    found_pages: set[str] = set()

    for file_path in template_files:
        sdk_refs, containers, page_layout = analyze_template_file(file_path, repo_root)
        all_sdk_refs.extend(sdk_refs)
        all_button_containers.extend(containers)

        page_type = _guess_page_type(file_path, file_path.read_text(encoding="utf-8", errors="replace"))
        if page_type != "unknown":
            found_pages.add(page_type)
        if containers:
            pages_with_buttons.add(page_type)

        if page_layout and layout is None:
            layout = page_layout

    # Identify pages that exist but lack PayPal button presentment
    missing_pages = sorted(found_pages - pages_with_buttons)

    return all_sdk_refs, all_button_containers, missing_pages, layout
