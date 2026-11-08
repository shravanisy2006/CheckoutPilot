"""
Browser configuration and lifecycle management using async Playwright.
Supports headless Chromium for local development and cloud containers (Render, Docker).
"""

import os
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from scanner.exceptions import BrowserLaunchError

# Chromium flags required/recommended for headless Linux containers (Render, Docker)
# as well as local headless execution.
DEFAULT_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


@dataclass
class BrowserConfig:
    """Configuration options for headless Chromium browser automation."""

    headless: bool = True
    timeout_ms: int = 30000
    navigation_timeout_ms: int = 15000
    action_timeout_ms: int = 2500
    screenshots_dir: str = "screenshots"
    viewport_desktop: dict[str, int] = field(
        default_factory=lambda: {"width": 1280, "height": 800}
    )
    viewport_mobile: dict[str, int] = field(
        default_factory=lambda: {"width": 375, "height": 667}
    )
    user_agent_desktop: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 CheckoutPilot/1.0"
    )
    user_agent_mobile: str = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1 CheckoutPilot/1.0"
    )
    chromium_args: list[str] = field(default_factory=lambda: list(DEFAULT_CHROMIUM_ARGS))

    @classmethod
    def from_env(cls) -> "BrowserConfig":
        """Load configuration with environment variable overrides if present."""
        headless_env = os.getenv("HEADLESS_BROWSER", "true").strip().lower()
        headless = headless_env not in ("false", "0", "no")

        timeout_env = os.getenv("BROWSER_TIMEOUT_MS", "30000").strip()
        try:
            timeout_ms = int(timeout_env)
        except ValueError:
            timeout_ms = 30000

        nav_timeout_env = os.getenv("BROWSER_NAV_TIMEOUT_MS", "15000").strip()
        try:
            navigation_timeout_ms = int(nav_timeout_env)
        except ValueError:
            navigation_timeout_ms = 15000

        action_timeout_env = os.getenv("BROWSER_ACTION_TIMEOUT_MS", "2500").strip()
        try:
            action_timeout_ms = int(action_timeout_env)
        except ValueError:
            action_timeout_ms = 2500

        screenshots_dir = os.getenv("SCREENSHOTS_DIR", "screenshots").strip()

        return cls(
            headless=headless,
            timeout_ms=timeout_ms,
            navigation_timeout_ms=navigation_timeout_ms,
            action_timeout_ms=action_timeout_ms,
            screenshots_dir=screenshots_dir,
        )


class PlaywrightBrowserSession:
    """
    Manages Playwright and Chromium browser lifecycle.

    Uses the async context manager protocol to guarantee browser and driver cleanup.
    Provides methods to create desktop and mobile contexts on a single browser
    instance, avoiding multiple browser launches.
    """

    def __init__(self, config: BrowserConfig | None = None) -> None:
        self.config = config or BrowserConfig.from_env()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    @property
    def browser(self) -> Browser:
        """Access the running browser instance."""
        if not self._browser or not self._browser.is_connected():
            raise BrowserLaunchError("Browser is not running or has been closed.")
        return self._browser

    async def __aenter__(self) -> "PlaywrightBrowserSession":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def start(self) -> Browser:
        """Launch Playwright and Chromium."""
        if self._browser and self._browser.is_connected():
            return self._browser

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.config.headless,
                args=self.config.chromium_args,
                timeout=self.config.timeout_ms,
            )
            return self._browser
        except Exception as exc:
            await self.close()
            raise BrowserLaunchError(f"Failed to launch Chromium browser: {exc}") from exc

    async def create_desktop_context(self) -> BrowserContext:
        """
        Create a desktop browser context on the existing browser instance.
        Avoids launching a new browser process.
        """
        return await self.browser.new_context(
            viewport=self.config.viewport_desktop,
            user_agent=self.config.user_agent_desktop,
        )

    async def create_mobile_context(self) -> BrowserContext:
        """
        Create a mobile browser context on the existing browser instance.
        Avoids launching a new browser process.
        """
        return await self.browser.new_context(
            viewport=self.config.viewport_mobile,
            user_agent=self.config.user_agent_mobile,
            is_mobile=True,
            has_touch=True,
        )

    async def close(self) -> None:
        """Close the browser and stop the Playwright driver cleanly."""
        if self._browser:
            try:
                if self._browser.is_connected():
                    await self._browser.close()
            except Exception:
                pass
            finally:
                self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            finally:
                self._playwright = None

    @classmethod
    async def verify_browser(cls, config: BrowserConfig | None = None) -> bool:
        """
        Diagnostic helper to verify that headless Chromium launches and closes cleanly.
        """
        async with cls(config=config) as session:
            return session.browser.is_connected()
