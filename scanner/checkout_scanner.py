"""
Checkout scanner (Playwright).

Opens an e-commerce store like a shopper would:
  product page -> cart -> checkout
and collects structured technical evidence (screenshots, page HTML, scripts, PayPal SDK
details, button/container positions, and Pay Later messaging) across both desktop and
mobile viewports.

Outputs a plain dictionary conforming to docs/architecture.md and backend/schemas/scan.py.
"""

import asyncio
import concurrent.futures
from typing import Any, Coroutine

from scanner.browser import BrowserConfig, PlaywrightBrowserSession
from scanner.navigator import StoreNavigator
from scanner.paypal_detector import (
    detect_overall_sdk_version,
    filter_paypal_scripts,
)
from scanner.selectors import NavigationSelectors
from scanner.url_validator import validate_url


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Safely execute an async coroutine from a synchronous caller.

    Handles regular synchronous environments, pytest, and threads
    with or without an active event loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


async def async_scan_store(
    store_url: str,
    include_mobile: bool = True,
    config: BrowserConfig | None = None,
    selectors: NavigationSelectors | None = None,
) -> dict[str, Any]:
    """
    Asynchronously walk an e-commerce store and collect technical checkout evidence.

    Args:
        store_url: Public URL of the store to scan (must be http/https).
        include_mobile: If True, also scan with a mobile viewport.
        config: Optional BrowserConfig override.
        selectors: Optional NavigationSelectors override.

    Returns:
        Structured scan data dictionary:
        {
            "store_url": str,
            "detected_sdk_version": "v4" | "v5" | "v6" | "unknown",
            "paypal_scripts": list[str],
            "paypal_presence": {
                "product": {"desktop": bool, "mobile": bool},
                "cart": {"desktop": bool, "mobile": bool},
                "checkout": {"desktop": bool, "mobile": bool},
            },
            "navigation_summary": dict,
            "pages": [
                {
                    "step": "product" | "cart" | "checkout",
                    "viewport": "desktop" | "mobile",
                    "url": str,
                    "title": str,
                    "screenshot_path": str,
                    "html": str,
                    "scripts": list[str],
                    "script_details": list[dict],
                    "paypal_elements": list[dict],
                    "pay_later_messaging": dict,
                    "success": bool,
                    "error": str,
                }
            ],
        }

    Raises:
        InvalidURLError: If the store URL is invalid or malformed.
        BrowserLaunchError: If Chromium fails to launch.
    """
    validated_url = validate_url(store_url)
    cfg = config or BrowserConfig.from_env()
    sel = selectors or NavigationSelectors()

    all_pages: list[dict[str, Any]] = []
    summary: dict[str, dict[str, bool]] = {
        "desktop": {"product": False, "cart": False, "checkout": False},
    }
    if include_mobile:
        summary["mobile"] = {"product": False, "cart": False, "checkout": False}

    async with PlaywrightBrowserSession(config=cfg) as session:
        # 1. Desktop Viewport Walk
        desktop_ctx = await session.create_desktop_context()
        try:
            desktop_page = await desktop_ctx.new_page()
            desktop_nav = StoreNavigator(desktop_page, config=cfg, selectors=sel)
            desktop_pages = await desktop_nav.walk_store(validated_url, viewport="desktop")
            all_pages.extend(desktop_pages)
            for page_data in desktop_pages:
                step = page_data.get("step")
                if step in summary["desktop"]:
                    summary["desktop"][step] = page_data.get("success", False)
        finally:
            await desktop_ctx.close()

        # 2. Mobile Viewport Walk (on the same browser instance)
        if include_mobile:
            mobile_ctx = await session.create_mobile_context()
            try:
                mobile_page = await mobile_ctx.new_page()
                mobile_nav = StoreNavigator(mobile_page, config=cfg, selectors=sel)
                mobile_pages = await mobile_nav.walk_store(validated_url, viewport="mobile")
                all_pages.extend(mobile_pages)
                for page_data in mobile_pages:
                    step = page_data.get("step")
                    if step in summary["mobile"]:
                        summary["mobile"][step] = page_data.get("success", False)
            finally:
                await mobile_ctx.close()

    # 3. Aggregate store-level PayPal evidence
    all_scripts = sorted(list({s for p in all_pages for s in p.get("scripts", [])}))
    detected_sdk_version = detect_overall_sdk_version(all_scripts)
    paypal_scripts = filter_paypal_scripts(all_scripts)

    presence: dict[str, dict[str, bool]] = {
        "product": {"desktop": False, "mobile": False},
        "cart": {"desktop": False, "mobile": False},
        "checkout": {"desktop": False, "mobile": False},
    }
    for page_data in all_pages:
        step = str(page_data.get("step", ""))
        vp = str(page_data.get("viewport", ""))
        has_elements = bool(page_data.get("paypal_elements"))
        if step in presence and vp in presence[step]:
            if has_elements:
                presence[step][vp] = True

    # 4. Determine overall scan status and aggregate errors/warnings
    total_steps = len(summary["desktop"])
    if include_mobile:
        total_steps += len(summary.get("mobile", {}))

    successful_steps = sum(
        1 for vp_data in summary.values() for ok in vp_data.values() if ok
    )

    if successful_steps == total_steps and total_steps > 0:
        status = "completed"
    elif successful_steps > 0:
        status = "partial"
    else:
        status = "failed"

    errors: list[str] = []
    warnings: list[str] = []
    for page_data in all_pages:
        err = page_data.get("error")
        if err and err not in errors:
            errors.append(err)
        for warn in page_data.get("warnings", []):
            if warn not in warnings:
                warnings.append(warn)

    return {
        "store_url": validated_url,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "detected_sdk_version": detected_sdk_version,
        "paypal_scripts": paypal_scripts,
        "paypal_presence": presence,
        "navigation_summary": summary,
        "pages": all_pages,
    }


def scan_store(
    store_url: str,
    include_mobile: bool = True,
    config: BrowserConfig | None = None,
    selectors: NavigationSelectors | None = None,
) -> dict[str, Any]:
    """
    Synchronous entry point for the checkout scanner.

    Invoked by backend/services/scan_service.py and test suites.
    Calls async_scan_store internally.
    """
    return _run_async(
        async_scan_store(
            store_url=store_url,
            include_mobile=include_mobile,
            config=config,
            selectors=selectors,
        )
    )


def detect_paypal_scripts(scripts: list[str]) -> list[str]:
    """
    Filter a list of script URLs and return only those belonging to PayPal.
    """
    return filter_paypal_scripts(scripts)


def detect_paypal_sdk_version(scripts: list[str]) -> str:
    """
    Identify the PayPal JavaScript SDK version from loaded script URLs.

    Returns:
        "v6" if Web SDK v6 is detected.
        "v5" if JavaScript SDK v5 (paypal.com/sdk/js) is detected.
        "v4" if legacy checkout.js (v4) is detected.
        "unknown" if the version cannot be determined.
        Never guesses versions.
    """
    return detect_overall_sdk_version(scripts)
