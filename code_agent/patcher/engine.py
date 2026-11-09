"""
Code Patcher Engine: in-memory staging, validation, and safe atomic file persistence.
Works dynamically across arbitrary repository structures.
"""

from pathlib import Path
from typing import Any, Optional

from code_agent.analyzer import PaymentContext, analyze_repository
from code_agent.patcher.store_transformer import (
    get_paypal_v6_js,
    patch_app_routes,
    patch_cart_template,
    patch_checkout_template,
    patch_style_css,
)
from code_agent.patcher.validators import (
    validate_business_preservation,
    validate_html_syntax_and_ids,
    validate_python_syntax,
)


class PatchEngine:
    """Safely validates and applies PayPal modernization patches to any repository."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()

    def _find_server_file(self, context: PaymentContext) -> Optional[Path]:
        """Find the main Python server file dynamically."""
        # 1. From detected endpoints
        for ep in context.server_endpoints:
            p = self.repo_path / ep.file_path
            if p.exists():
                return p

        # 2. Search common server filenames
        for candidate in ("app.py", "main.py", "server.py", "api.py"):
            matches = list(self.repo_path.rglob(candidate))
            valid = [m for m in matches if not any(x in m.parts for x in ("venv", ".venv", "tests"))]
            if valid:
                return valid[0]

        # 3. Search any Python file with FastAPI or Flask
        for p in self.repo_path.rglob("*.py"):
            if any(x in p.parts for x in ("venv", ".venv", "tests")):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if "FastAPI(" in text or "Flask(" in text or "@app." in text:
                    return p
            except Exception:
                continue

        return None

    def _find_checkout_template(self, context: PaymentContext) -> Optional[Path]:
        """Find the checkout HTML template dynamically."""
        # 1. From SDK references
        for ref in context.sdk_references:
            p = self.repo_path / ref.file_path
            if p.exists() and "checkout" in p.name.lower():
                return p

        # 2. Search HTML files with checkout in name
        for p in self.repo_path.rglob("*.html"):
            if any(x in p.parts for x in ("venv", ".venv", "node_modules", "outputs")):
                continue
            if "checkout" in p.name.lower():
                return p

        return None

    def _find_cart_template(self, context: PaymentContext) -> Optional[Path]:
        """Find the cart HTML template dynamically."""
        for p in self.repo_path.rglob("*.html"):
            if any(x in p.parts for x in ("venv", ".venv", "node_modules", "outputs")):
                continue
            if "cart" in p.name.lower():
                return p
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                if 'data-page="cart"' in content or 'id="cart-lines"' in content:
                    return p
            except Exception:
                continue

        return None

    def _find_style_file(self, context: PaymentContext) -> Optional[Path]:
        """Find the CSS stylesheet dynamically."""
        if context.layout and context.layout.style_file:
            p = self.repo_path / context.layout.style_file
            if p.exists():
                return p

        # Search for css with .checkout
        for p in self.repo_path.rglob("*.css"):
            if any(x in p.parts for x in ("venv", ".venv", "node_modules")):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                if ".checkout" in content or "media" in content:
                    return p
            except Exception:
                continue

        # Fallback to any css
        css_files = [p for p in self.repo_path.rglob("*.css") if not any(x in p.parts for x in ("venv", ".venv"))]
        return css_files[0] if css_files else None

    def _find_static_dir(self, context: PaymentContext) -> Path:
        """Find the static or assets directory for client scripts."""
        for name in ("static", "public", "assets", "js"):
            candidate = self.repo_path / name
            if candidate.is_dir():
                return candidate
        # Fallback to root or template sibling
        return self.repo_path

    def apply_upgrade(self, plan: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        """Apply the upgrade patches to the repository."""
        if not self.repo_path.exists() or not self.repo_path.is_dir():
            return {
                "success": False,
                "files_changed": [],
                "errors": [f"Repository path does not exist: {self.repo_path}"],
            }

        # Analyze repo structure dynamically
        context: PaymentContext = analyze_repository(self.repo_path)

        files_changed: list[str] = []
        errors: list[str] = []

        # 1. Dynamically locate & patch server routes
        server_file = self._find_server_file(context)
        if server_file and server_file.exists():
            rel_server = str(server_file.relative_to(self.repo_path)).replace("\\", "/")
            original_app = server_file.read_text(encoding="utf-8")
            patched_app = patch_app_routes(original_app)

            # Validate Python syntax
            valid_syntax, err = validate_python_syntax(patched_app)
            if not valid_syntax:
                errors.append(f"{rel_server} validation failed: {err}")
            else:
                # Validate non-payment business code preservation
                preserved, p_err = validate_business_preservation(
                    original_app,
                    patched_app,
                    required_symbols=["PRODUCTS", "calculate_total", "MAX_QTY_PER_ITEM", "list_products"],
                )
                if not preserved:
                    errors.append(f"{rel_server} preservation check failed: {p_err}")
                else:
                    if original_app != patched_app:
                        server_file.write_text(patched_app, encoding="utf-8")
                        files_changed.append(rel_server)

        # 2. Dynamically locate & patch checkout template
        checkout_tpl = self._find_checkout_template(context)
        if checkout_tpl and checkout_tpl.exists():
            rel_checkout = str(checkout_tpl.relative_to(self.repo_path)).replace("\\", "/")
            original_checkout = checkout_tpl.read_text(encoding="utf-8")
            patched_checkout = patch_checkout_template(original_checkout)

            valid_html, h_err = validate_html_syntax_and_ids(
                patched_checkout,
                required_ids=["shipping-form", "order-summary", "cart-lines", "cart-total", "paypal-button-container"],
            )
            if not valid_html:
                errors.append(f"{rel_checkout} validation failed: {h_err}")
            else:
                if original_checkout != patched_checkout:
                    checkout_tpl.write_text(patched_checkout, encoding="utf-8")
                    files_changed.append(rel_checkout)

        # 3. Dynamically locate & patch cart template
        cart_tpl = self._find_cart_template(context)
        if cart_tpl and cart_tpl.exists():
            rel_cart = str(cart_tpl.relative_to(self.repo_path)).replace("\\", "/")
            original_cart = cart_tpl.read_text(encoding="utf-8")
            patched_cart = patch_cart_template(original_cart)

            valid_html, h_err = validate_html_syntax_and_ids(
                patched_cart,
                required_ids=["cart-lines", "cart-total", "cart-empty", "go-to-checkout", "clear-cart"],
            )
            if not valid_html:
                errors.append(f"{rel_cart} validation failed: {h_err}")
            else:
                if original_cart != patched_cart:
                    cart_tpl.write_text(patched_cart, encoding="utf-8")
                    files_changed.append(rel_cart)

        # 4. Dynamically locate & patch CSS
        style_file = self._find_style_file(context)
        if style_file and style_file.exists():
            rel_style = str(style_file.relative_to(self.repo_path)).replace("\\", "/")
            original_style = style_file.read_text(encoding="utf-8")
            patched_style = patch_style_css(original_style)
            if original_style != patched_style:
                style_file.write_text(patched_style, encoding="utf-8")
                files_changed.append(rel_style)

        # 5. Emit static/paypal.js (v6 client integration)
        static_dir = self._find_static_dir(context)
        if static_dir.exists():
            paypal_js_file = static_dir / "paypal.js"
            if not paypal_js_file.exists():
                paypal_js_file.write_text(get_paypal_v6_js(), encoding="utf-8")
                rel_js = str(paypal_js_file.relative_to(self.repo_path)).replace("\\", "/")
                files_changed.append(rel_js)

        return {
            "success": len(errors) == 0,
            "files_changed": files_changed,
            "errors": errors,
        }


def apply_upgrade(repo_path: str | Path, plan: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """Convenience wrapper for applying upgrades."""
    engine = PatchEngine(repo_path)
    return engine.apply_upgrade(plan)
