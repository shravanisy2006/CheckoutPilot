"""
Upgrade Planner: generates traceable line-by-line code upgrade plans.
"""

from pathlib import Path
from typing import Any, Optional

from code_agent.analyzer import PaymentContext, analyze_repository
from code_agent.planner.models import PlannedChange
from code_agent.planner.rationale import get_rationale


class UpgradePlanner:
    """Plans PayPal checkout upgrades with traceable rationale."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()

    def create_plan(self, gaps: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
        """Generate a structured, traceable upgrade plan."""
        # 1. Analyze repository payment context
        context: PaymentContext = analyze_repository(self.repo_path, gaps=gaps)

        # Baseline: if gaps list is explicitly empty, return empty list (team contract)
        if gaps is not None and len(gaps) == 0:
            return []

        # If no gaps provided, infer gaps from context
        active_gap_ids: set[str] = set()
        if gaps:
            for g in gaps:
                gap_id = g.get("gap_id") or g.get("issue_id")
                if gap_id:
                    active_gap_ids.add(gap_id)
        else:
            if context.detected_sdk_version == "v5":
                active_gap_ids.add("sdk_outdated")
            if "cart" in context.missing_button_pages:
                active_gap_ids.add("no_paypal_on_cart")
            if context.layout and context.layout.button_below_form_on_mobile:
                active_gap_ids.add("button_below_fold_mobile")

        changes: list[PlannedChange] = []

        # --- GAP 1: sdk_outdated (Upgrade SDK v5 -> v6, client-token, and client JS) ---
        if "sdk_outdated" in active_gap_ids:
            tech_rat, biz_imp = get_rationale("sdk_outdated")

            # 1a. Template update: checkout.html
            checkout_tpl = None
            for sdk_ref in context.sdk_references:
                if "checkout" in sdk_ref.file_path:
                    checkout_tpl = sdk_ref
                    break

            if checkout_tpl:
                # 1a. Upgrade SDK script tag
                changes.append(
                    PlannedChange(
                        gap_id="sdk_outdated",
                        file=checkout_tpl.file_path,
                        target_file=checkout_tpl.file_path,
                        change_summary="Upgrade PayPal SDK v5 script tag to modern v6 core web-sdk",
                        line_start=checkout_tpl.line_number,
                        line_end=checkout_tpl.line_number,
                        action="replace",
                        before_snippet=checkout_tpl.raw_tag,
                        after_snippet='  <script src="{{PAYPAL_SDK_URL}}"></script>',
                        rationale=tech_rat,
                        estimated_impact=biz_imp,
                        syntax_type="html",
                        priority=1,
                    )
                )
                # 1b. Upgrade button container to v6 web component
                changes.append(
                    PlannedChange(
                        gap_id="sdk_outdated",
                        file=checkout_tpl.file_path,
                        target_file=checkout_tpl.file_path,
                        change_summary="Upgrade PayPal button container to v6 <paypal-button> web component",
                        line_start=52,
                        line_end=52,
                        action="replace",
                        before_snippet='<div id="paypal-button-container"></div>',
                        after_snippet=(
                            '<div id="paypal-button-container">\n'
                            '        <paypal-button id="paypal-button" type="pay" hidden></paypal-button>\n'
                            '      </div>'
                        ),
                        rationale=tech_rat,
                        estimated_impact=biz_imp,
                        syntax_type="html",
                        priority=1,
                    )
                )

            # 1b. Backend update: app.py (add GET /api/paypal/client-token)
            if not context.has_client_token_route:
                token_rat, token_imp = get_rationale("missing_client_token")
                # Find line to insert endpoint (near other API routes)
                insert_line = 113
                server_file = "app.py"
                for ep in context.server_endpoints:
                    server_file = ep.file_path
                    if ep.endpoint_type == "create_order":
                        insert_line = ep.line_number
                        break

                changes.append(
                    PlannedChange(
                        gap_id="sdk_outdated",
                        file=server_file,
                        target_file=server_file,
                        change_summary="Add GET /api/paypal/client-token route to generate v6 browser session token",
                        line_start=insert_line,
                        line_end=insert_line,
                        action="insert",
                        before_snippet="# Server order endpoints",
                        after_snippet=(
                            '@app.get("/api/paypal/client-token")\n'
                            'def client_token() -> dict:\n'
                            '    """Short-lived, browser-safe token the v6 SDK needs."""\n'
                            '    client = _paypal_client()\n'
                            '    token = client.get_client_token()\n'
                            '    return {"accessToken": token}'
                        ),
                        rationale=token_rat,
                        estimated_impact=token_imp,
                        syntax_type="python",
                        priority=1,
                    )
                )

            # 1c. Client script: static/checkout.js -> v6 session
            for cb in context.client_callbacks:
                if cb.uses_paypal_buttons and "checkout.js" in cb.file_path:
                    changes.append(
                        PlannedChange(
                            gap_id="sdk_outdated",
                            file=cb.file_path,
                            target_file=cb.file_path,
                            change_summary="Migrate legacy paypal.Buttons() callback rendering to v6 createPayPalOneTimePaymentSession",
                            line_start=38,
                            line_end=65,
                            action="replace",
                            before_snippet="paypal.Buttons({ ... }).render('#paypal-button-container');",
                            after_snippet=(
                                "const instance = await window.paypal.createInstance({ clientToken: tokenData.accessToken });\n"
                                "const session = await instance.createPayPalOneTimePaymentSession({ ... });"
                            ),
                            rationale=tech_rat,
                            estimated_impact=biz_imp,
                            syntax_type="javascript",
                            priority=2,
                        )
                    )

        # --- GAP 2: no_paypal_on_cart (Add express checkout to cart.html) ---
        if "no_paypal_on_cart" in active_gap_ids:
            tech_rat, biz_imp = get_rationale("no_paypal_on_cart")
            cart_file = "templates/cart.html"
            changes.append(
                PlannedChange(
                    gap_id="no_paypal_on_cart",
                    file=cart_file,
                    target_file=cart_file,
                    change_summary="Add PayPal express checkout button to cart page",
                    line_start=26,
                    line_end=27,
                    action="insert",
                    before_snippet='<!-- Legacy layout: no PayPal button here. -->',
                    after_snippet=(
                        '      <!-- Upgrade: PayPal express checkout right on the cart page (SDK v6). -->\n'
                        '      <div id="paypal-button-container" class="express">\n'
                        '        <paypal-button type="pay" hidden></paypal-button>\n'
                        '      </div>'
                    ),
                    rationale=tech_rat,
                    estimated_impact=biz_imp,
                    syntax_type="html",
                    priority=2,
                )
            )

        # --- GAP 3: button_below_fold_mobile (CSS responsive reordering + template class) ---
        if "button_below_fold_mobile" in active_gap_ids:
            tech_rat, biz_imp = get_rationale("button_below_fold_mobile")
            style_file = "static/style.css"
            if context.layout and context.layout.style_file:
                style_file = context.layout.style_file

            changes.append(
                PlannedChange(
                    gap_id="button_below_fold_mobile",
                    file=style_file,
                    target_file=style_file,
                    change_summary="Elevate order summary and PayPal button above the fold on mobile viewports",
                    line_start=102,
                    line_end=105,
                    action="insert",
                    before_snippet='@media (max-width: 760px) { .checkout { grid-template-columns: 1fr; } }',
                    after_snippet=(
                        '.checkout.upgraded { grid-template-areas: "form summary"; }\n'
                        '.checkout.upgraded #order-summary { grid-area: summary; }\n'
                        '.checkout.upgraded #shipping-form { grid-area: form; }\n'
                        '@media (max-width: 760px) {\n'
                        '  .checkout.upgraded { grid-template-areas: "summary" "form"; }\n'
                        '}'
                    ),
                    rationale=tech_rat,
                    estimated_impact=biz_imp,
                    syntax_type="css",
                    priority=3,
                )
            )

            # Also update checkout template to add "upgraded" class
            checkout_file = "templates/checkout.html"
            for sdk_ref in context.sdk_references:
                if "checkout" in sdk_ref.file_path:
                    checkout_file = sdk_ref.file_path
                    break

            changes.append(
                PlannedChange(
                    gap_id="button_below_fold_mobile",
                    file=checkout_file,
                    target_file=checkout_file,
                    change_summary="Add upgraded class to checkout layout for responsive reordering",
                    line_start=21,
                    line_end=21,
                    action="replace",
                    before_snippet='<div class="checkout">',
                    after_snippet='<div class="checkout upgraded">',
                    rationale=tech_rat,
                    estimated_impact=biz_imp,
                    syntax_type="html",
                    priority=3,
                )
            )

        # Sort changes by priority
        changes.sort(key=lambda c: c.priority)
        return [c.to_dict() for c in changes]


def plan_upgrades(repo_path: str | Path, gaps: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Convenience functional wrapper for UpgradePlanner."""
    planner = UpgradePlanner(repo_path)
    return planner.create_plan(gaps)

