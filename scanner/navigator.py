"""
Store navigator for the CheckoutPilot scanner.
Executes the product -> cart -> checkout navigation flow with resilient fallbacks,
timeouts, screenshot capture, and script/DOM element extraction.
"""

import os
import time
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from scanner.browser import BrowserConfig
from scanner.paypal_detector import detect_paypal_elements, parse_script_details
from scanner.selectors import NavigationSelectors


class StoreNavigator:
    """
    Navigates an e-commerce store across product -> cart -> checkout pages.
    Captures screenshots, HTML, script URLs, and PayPal-related elements at each stage.
    """

    def __init__(
        self,
        page: Page,
        config: BrowserConfig | None = None,
        selectors: NavigationSelectors | None = None,
    ) -> None:
        self.page = page
        self.config = config or BrowserConfig.from_env()
        self.selectors = selectors or NavigationSelectors()
        self.captured_scripts: set[str] = set()

        # Intercept network requests to capture loaded JavaScript files
        self.page.on("request", self._on_request)

    def _on_request(self, request: Any) -> None:
        """Collect URLs of all JavaScript resources requested by the page."""
        try:
            url = request.url
            if request.resource_type == "script" or ".js" in url:
                self.captured_scripts.add(url)
        except Exception:
            pass

    async def find_first(
        self,
        selectors: list[str],
        timeout_ms: int | None = None,
    ) -> tuple[Locator | None, str | None]:
        """
        Find the first matching locator from a list of selectors.

        Checks immediately if an element is already attached and visible.
        If not found immediately, waits briefly for the first priority selector.

        Returns:
            Tuple of (Locator, matching_selector) or (None, None).
        """
        timeout = timeout_ms if timeout_ms is not None else self.config.action_timeout_ms

        # 1. Quick check for any selector already visible in the DOM
        for sel in selectors:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc, sel
            except Exception:
                continue

        # 2. Brief wait for the primary selector (e.g. client-side hydration)
        if selectors:
            primary_sel = selectors[0]
            try:
                loc = self.page.locator(primary_sel).first
                await loc.wait_for(state="visible", timeout=timeout)
                return loc, primary_sel
            except Exception:
                pass

        return None, None

    async def find_and_click(
        self,
        selectors: list[str],
        timeout_ms: int | None = None,
    ) -> tuple[bool, str | None]:
        """
        Attempt to find and click the first matching selector.

        Returns:
            Tuple of (success_bool, matched_selector_or_None).
        """
        loc, sel = await self.find_first(selectors, timeout_ms=timeout_ms)
        if loc and sel:
            try:
                await loc.scroll_into_view_if_needed(timeout=1500)
                await loc.click(timeout=self.config.action_timeout_ms)
                return True, sel
            except Exception:
                pass
        return False, None

    async def capture_page_evidence(
        self,
        step: str,
        viewport: str,
        success: bool = True,
        error: str = "",
        warnings: list[str] | None = None,
    ) -> dict:
        """
        Capture screenshots, page HTML, loaded script URLs, and PayPal elements.

        Returns a dictionary conforming to the CheckoutPilot scanner schema.
        """
        current_url = self.page.url or ""
        current_title = ""
        try:
            current_title = await self.page.title()
        except Exception:
            pass

        # 1. Capture screenshot
        screenshot_path = ""
        try:
            os.makedirs(self.config.screenshots_dir, exist_ok=True)
            filename = f"scan_{int(time.time() * 1000)}_{viewport}_{step}.png"
            full_path = os.path.abspath(os.path.join(self.config.screenshots_dir, filename))
            await self.page.screenshot(path=full_path, full_page=False, timeout=5000)
            screenshot_path = full_path
        except Exception:
            screenshot_path = ""

        # 2. Capture page HTML
        html_content = ""
        try:
            html_content = await self.page.content()
        except Exception:
            pass

        # 3. Collect script URLs and inspect PayPal SDK details
        dom_scripts: list[str] = []
        try:
            dom_scripts = await self.page.eval_on_selector_all(
                "script[src]",
                "elements => elements.map(e => e.src).filter(Boolean)",
            )
        except Exception:
            pass

        all_scripts = sorted(list(self.captured_scripts.union(dom_scripts)))
        script_details = [parse_script_details(s) for s in all_scripts]

        # 4. Detect PayPal-related elements and Pay Later messaging on the page
        paypal_elements, pay_later_messaging = await detect_paypal_elements(
            self.page,
            selectors=self.selectors,
        )

        # Check if messaging component was requested in any loaded script URL
        script_has_messaging = any(
            "messages" in detail.get("components", [])
            for detail in script_details
            if detail.get("is_paypal")
        )
        pay_later_messaging["script_component_present"] = script_has_messaging
        if script_has_messaging:
            pay_later_messaging["detected"] = True

        return {
            "step": step,
            "viewport": viewport,
            "url": current_url,
            "title": current_title,
            "screenshot_path": screenshot_path,
            "html": html_content,
            "scripts": all_scripts,
            "script_details": script_details,
            "paypal_elements": paypal_elements,
            "pay_later_messaging": pay_later_messaging,
            "success": success,
            "error": error,
            "warnings": list(warnings or []),
        }

    async def walk_store(self, store_url: str, viewport: str = "desktop") -> list[dict]:
        """
        Execute the product -> cart -> checkout navigation workflow.

        Captures evidence at each step, tolerating missing elements and navigation
        failures gracefully without crashing the overall scan.

        Returns:
            List of evidence dictionaries for each visited stage.
        """
        pages: list[dict] = []

        # =====================================================================
        # Step 1: Open Store / Identify Product Page
        # =====================================================================
        try:
            await self.page.goto(
                store_url,
                wait_until="domcontentloaded",
                timeout=self.config.navigation_timeout_ms,
            )
            await self.page.wait_for_timeout(800)
        except (PlaywrightTimeoutError, Exception) as exc:
            # Fatal initial navigation failure: record error and stop viewport run
            failed_evidence = await self.capture_page_evidence(
                step="product",
                viewport=viewport,
                success=False,
                error=f"Failed to open store URL: {exc}",
            )
            pages.append(failed_evidence)
            return pages

        # Check if we landed on a product page (e.g. Add to Cart button already present)
        product_warnings: list[str] = []
        add_to_cart_loc, _ = await self.find_first(self.selectors.add_to_cart, timeout_ms=1000)
        if not add_to_cart_loc:
            # Landed on catalog or home page: find and click a product link
            clicked_product, _ = await self.find_and_click(
                self.selectors.product_links,
                timeout_ms=1500,
            )
            if clicked_product:
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=4000)
                except Exception:
                    pass
                await self.page.wait_for_timeout(800)
            else:
                product_warnings.append(
                    "No distinct product link or Add to Cart button detected; captured landing page."
                )

        # Record product step evidence
        product_evidence = await self.capture_page_evidence(
            step="product",
            viewport=viewport,
            warnings=product_warnings,
        )
        pages.append(product_evidence)

        # =====================================================================
        # Step 2: Add to Cart and Navigate to Cart Page
        # =====================================================================
        cart_step_success = True
        cart_step_error = ""
        cart_warnings: list[str] = []

        # Click Add to Cart
        clicked_cart_btn, _ = await self.find_and_click(
            self.selectors.add_to_cart,
            timeout_ms=self.config.action_timeout_ms,
        )
        if clicked_cart_btn:
            await self.page.wait_for_timeout(1000)
        else:
            cart_warnings.append("Add to Cart button was not found on product page.")

        # If not redirected to cart automatically, find and click Go to Cart
        current_url_lower = (self.page.url or "").lower()
        if "/cart" not in current_url_lower and "/basket" not in current_url_lower:
            navigated_to_cart, _ = await self.find_and_click(
                self.selectors.go_to_cart,
                timeout_ms=self.config.action_timeout_ms,
            )
            if navigated_to_cart:
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=4000)
                except Exception:
                    pass
                await self.page.wait_for_timeout(800)
            else:
                # Direct URL fallback to /cart
                cart_warnings.append("Go to Cart button was not found; attempted direct /cart URL.")
                try:
                    cart_url = urljoin(store_url, "/cart")
                    await self.page.goto(
                        cart_url,
                        wait_until="domcontentloaded",
                        timeout=self.config.navigation_timeout_ms,
                    )
                    await self.page.wait_for_timeout(800)
                except Exception as exc:
                    cart_step_success = False
                    cart_step_error = f"Cart navigation failed: {exc}"

        # Record cart step evidence
        cart_evidence = await self.capture_page_evidence(
            step="cart",
            viewport=viewport,
            success=cart_step_success,
            error=cart_step_error,
            warnings=cart_warnings,
        )
        pages.append(cart_evidence)

        # =====================================================================
        # Step 3: Navigate to Checkout Page
        # =====================================================================
        checkout_step_success = True
        checkout_step_error = ""
        checkout_warnings: list[str] = []

        current_url_lower = (self.page.url or "").lower()
        if "/checkout" not in current_url_lower:
            # Click Go to Checkout
            navigated_to_checkout, _ = await self.find_and_click(
                self.selectors.go_to_checkout,
                timeout_ms=self.config.action_timeout_ms,
            )
            if navigated_to_checkout:
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=4000)
                except Exception:
                    pass
                await self.page.wait_for_timeout(800)
            else:
                # Direct URL fallback to /checkout
                checkout_warnings.append("Go to Checkout button was not found; attempted direct /checkout URL.")
                try:
                    checkout_url = urljoin(store_url, "/checkout")
                    await self.page.goto(
                        checkout_url,
                        wait_until="domcontentloaded",
                        timeout=self.config.navigation_timeout_ms,
                    )
                    await self.page.wait_for_timeout(800)
                except Exception as exc:
                    checkout_step_success = False
                    checkout_step_error = f"Checkout navigation failed: {exc}"

        # Record checkout step evidence
        checkout_evidence = await self.capture_page_evidence(
            step="checkout",
            viewport=viewport,
            success=checkout_step_success,
            error=checkout_step_error,
            warnings=checkout_warnings,
        )
        pages.append(checkout_evidence)

        return pages

