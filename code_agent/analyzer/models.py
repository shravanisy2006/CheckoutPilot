"""
Models representing the analyzed payment context of a store repository.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class SdkReference:
    """Represents a PayPal SDK script inclusion found in templates or scripts."""
    file_path: str
    line_number: int
    raw_tag: str
    version: str  # e.g. "v5", "v6", "unknown"
    client_id_param: Optional[str] = None
    components_param: Optional[str] = None
    currency_param: Optional[str] = None
    is_v6: bool = False


@dataclass
class ButtonContainer:
    """A DOM container or custom element where a PayPal button renders."""
    file_path: str
    line_number: int
    element_id: str
    element_type: str  # "container" (e.g. #paypal-button-container) or "custom_element" (<paypal-button>)
    page_type: str  # "checkout", "cart", "product", "unknown"


@dataclass
class ClientCallbackAnalysis:
    """Analysis of client-side JavaScript payment flows."""
    file_path: str
    uses_paypal_buttons: bool = False  # legacy v5 paypal.Buttons()
    uses_v6_instance: bool = False     # modern v6 createInstance()
    create_order_endpoint: Optional[str] = None
    capture_endpoint: Optional[str] = None
    client_token_endpoint: Optional[str] = None


@dataclass
class ServerEndpoint:
    """A backend route handling payment logic."""
    file_path: str
    line_number: int
    http_method: str  # GET, POST
    path: str         # e.g. /api/orders, /api/paypal/client-token
    endpoint_type: str  # "create_order", "capture_order", "client_token", "other"
    framework: str = "fastapi"  # "fastapi", "flask"


@dataclass
class LayoutAnalysis:
    """Analysis of button positioning, especially for mobile viewports."""
    template_file: str
    style_file: Optional[str] = None
    button_below_form_on_mobile: bool = False
    shipping_form_line: Optional[int] = None
    summary_container_line: Optional[int] = None


@dataclass
class PaymentContext:
    """Complete aggregated payment context for a store repository."""
    repo_path: str
    sdk_references: list[SdkReference] = field(default_factory=list)
    button_containers: list[ButtonContainer] = field(default_factory=list)
    missing_button_pages: list[str] = field(default_factory=list)
    client_callbacks: list[ClientCallbackAnalysis] = field(default_factory=list)
    server_endpoints: list[ServerEndpoint] = field(default_factory=list)
    layout: Optional[LayoutAnalysis] = None
    detected_sdk_version: str = "unknown"  # "v5", "v6", "missing"
    has_client_token_route: bool = False
    has_create_order_route: bool = False
    has_capture_order_route: bool = False
    warnings: list[str] = field(default_factory=list)
    guided_gaps: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass to standard Python dictionary for module boundaries."""
        return asdict(self)
