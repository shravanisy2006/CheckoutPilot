"""
Universal Code Patcher Engine: executes plan-driven and LLM-driven code patches
across any tech stack, with strict multi-language syntax and business preservation guards.
"""

from pathlib import Path
from typing import Any, Optional

from code_agent.analyzer import PaymentContext, analyze_repository
from code_agent.llm_client import BaseLLMAdapter, get_llm_client
from code_agent.patcher.llm_patcher import synthesize_file_patch
from code_agent.patcher.store_transformer import (
    get_paypal_v6_js,
    patch_app_routes,
    patch_cart_template,
    patch_checkout_template,
    patch_style_css,
)
from code_agent.patcher.validators import (
    validate_business_preservation,
    validate_code_syntax,
    validate_html_syntax_and_ids,
    validate_python_syntax,
)


class PatchEngine:
    """Safely validates and applies PayPal modernization patches to any repository."""

    def __init__(self, repo_path: str | Path, llm: Optional[BaseLLMAdapter] = None):
        self.repo_path = Path(repo_path).resolve()
        self.llm = llm or get_llm_client()

    def _find_server_file(self, context: PaymentContext) -> Optional[Path]:
        """Find the main server file dynamically."""
        for ep in context.server_endpoints:
            p = self.repo_path / ep.file_path
            if p.exists():
                return p

        for candidate in ("app.py", "main.py", "server.py", "api.py", "server.js", "app.js", "index.js"):
            matches = list(self.repo_path.rglob(candidate))
            valid = [m for m in matches if not any(x in m.parts for x in ("venv", ".venv", "tests", "node_modules"))]
            if valid:
                return valid[0]

        return None

    def _find_checkout_template(self, context: PaymentContext) -> Optional[Path]:
        """Find the checkout HTML template dynamically."""
        for ref in context.sdk_references:
            p = self.repo_path / ref.file_path
            if p.exists() and "checkout" in p.name.lower():
                return p

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

        for p in self.repo_path.rglob("*.css"):
            if any(x in p.parts for x in ("venv", ".venv", "node_modules")):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                if ".checkout" in content or "media" in content:
                    return p
            except Exception:
                continue

        css_files = [p for p in self.repo_path.rglob("*.css") if not any(x in p.parts for x in ("venv", ".venv"))]
        return css_files[0] if css_files else None

    def _find_static_dir(self, context: PaymentContext) -> Path:
        """Find the static or assets directory for client scripts."""
        for name in ("static", "public", "assets", "js"):
            candidate = self.repo_path / name
            if candidate.is_dir():
                return candidate
        return self.repo_path

    def _apply_plan_items(self, plan: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
        """Apply targeted changes directly from the LLM-generated plan."""
        files_changed = []
        errors = []

        # Group changes by target file
        files_map: dict[str, list[dict[str, Any]]] = {}
        for item in plan:
            target = item.get("target_file") or item.get("file")
            if target:
                files_map.setdefault(target, []).append(item)

        for rel_file, items in files_map.items():
            file_path = self.repo_path / rel_file
            if not file_path.exists():
                continue

            try:
                original_text = file_path.read_text(encoding="utf-8")
            except Exception as e:
                errors.append(f"Could not read {rel_file}: {e}")
                continue

            current_text = original_text
            applied_any = False

            # Try direct snippet substitution first
            for item in items:
                before = item.get("before_snippet", "").strip()
                after = item.get("after_snippet", "").strip()
                if before and before in current_text and after:
                    current_text = current_text.replace(before, after, 1)
                    applied_any = True

            # If direct snippet substitution did not match or LLM synthesis is desired
            if not applied_any and self.llm and self.llm.is_available() and type(self.llm).__name__ != "DeterministicFallbackAdapter":
                change_summary = "; ".join(it.get("change_summary", "") for it in items)
                synthesized = synthesize_file_patch(rel_file, original_text, change_summary, llm=self.llm)
                if synthesized:
                    current_text = synthesized
                    applied_any = True

            if applied_any and current_text != original_text:
                # Validate syntax and business preservation
                valid_syntax, s_err = validate_code_syntax(current_text, file_path)
                preserved, p_err = validate_business_preservation(original_text, current_text)

                if not valid_syntax:
                    errors.append(f"{rel_file} syntax check failed: {s_err}")
                elif not preserved:
                    errors.append(f"{rel_file} business preservation check failed: {p_err}")
                else:
                    file_path.write_text(current_text, encoding="utf-8")
                    files_changed.append(rel_file)

        return files_changed, errors

    def apply_upgrade(self, plan: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        """Apply the upgrade patches to the repository."""
        if not self.repo_path.exists() or not self.repo_path.is_dir():
            return {
                "success": False,
                "files_changed": [],
                "errors": [f"Repository path does not exist: {self.repo_path}"],
            }

        files_changed: list[str] = []
        errors: list[str] = []

        # 1. If an explicit plan was provided, execute plan-driven patching
        if plan:
            plan_files, plan_errors = self._apply_plan_items(plan)
            files_changed.extend(plan_files)
            errors.extend(plan_errors)

        # 2. Dynamic auto-transformer fallback for standard store files
        context: PaymentContext = analyze_repository(self.repo_path)

        # Server file
        server_file = self._find_server_file(context)
        if server_file and server_file.exists():
            rel_server = str(server_file.relative_to(self.repo_path)).replace("\\", "/")
            original_app = server_file.read_text(encoding="utf-8")
            patched_app = patch_app_routes(original_app)

            valid_syntax, err = validate_code_syntax(patched_app, server_file)
            preserved, p_err = validate_business_preservation(
                original_app, patched_app, required_symbols=["PRODUCTS", "calculate_total"]
            )

            if valid_syntax and preserved and original_app != patched_app:
                server_file.write_text(patched_app, encoding="utf-8")
                if rel_server not in files_changed:
                    files_changed.append(rel_server)

        # Checkout template
        checkout_tpl = self._find_checkout_template(context)
        if checkout_tpl and checkout_tpl.exists():
            rel_checkout = str(checkout_tpl.relative_to(self.repo_path)).replace("\\", "/")
            original_checkout = checkout_tpl.read_text(encoding="utf-8")
            patched_checkout = patch_checkout_template(original_checkout)

            valid_html, h_err = validate_html_syntax_and_ids(
                patched_checkout,
                required_ids=["shipping-form", "order-summary", "cart-lines", "cart-total", "paypal-button-container"],
            )
            if valid_html and original_checkout != patched_checkout:
                checkout_tpl.write_text(patched_checkout, encoding="utf-8")
                if rel_checkout not in files_changed:
                    files_changed.append(rel_checkout)

        # Cart template
        cart_tpl = self._find_cart_template(context)
        if cart_tpl and cart_tpl.exists():
            rel_cart = str(cart_tpl.relative_to(self.repo_path)).replace("\\", "/")
            original_cart = cart_tpl.read_text(encoding="utf-8")
            patched_cart = patch_cart_template(original_cart)

            valid_html, h_err = validate_html_syntax_and_ids(
                patched_cart,
                required_ids=["cart-lines", "cart-total", "cart-empty", "go-to-checkout", "clear-cart"],
            )
            if valid_html and original_cart != patched_cart:
                cart_tpl.write_text(patched_cart, encoding="utf-8")
                if rel_cart not in files_changed:
                    files_changed.append(rel_cart)

        # Style file (if not already patched)
        style_file = self._find_style_file(context)
        if style_file and style_file.exists():
            rel_style = str(style_file.relative_to(self.repo_path)).replace("\\", "/")
            if rel_style not in files_changed:
                original_style = style_file.read_text(encoding="utf-8")
                patched_style = patch_style_css(original_style)
                if original_style != patched_style:
                    style_file.write_text(patched_style, encoding="utf-8")
                    files_changed.append(rel_style)

        # Client v6 script
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


def apply_upgrade(
    repo_path: str | Path,
    plan: Optional[list[dict[str, Any]]] = None,
    llm: Optional[BaseLLMAdapter] = None,
) -> dict[str, Any]:
    """Convenience wrapper for applying upgrades."""
    engine = PatchEngine(repo_path, llm=llm)
    return engine.apply_upgrade(plan)
