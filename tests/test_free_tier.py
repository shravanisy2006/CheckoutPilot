"""FREE_TIER=true (Render free plan): low-memory Chromium, slower waits, stores in-process, one job at a time.
Run: pytest tests/test_free_tier.py -v"""

import asyncio
import socket

import requests

from backend.core import free_tier


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("FREE_TIER", raising=False)
    assert free_tier.apply() is False


def test_low_memory_args_are_added_once_and_keep_existing_args():
    args = free_tier.merge_args(["--disable-blink-features=AutomationControlled", "--disable-gpu"])
    assert args[0] == "--disable-blink-features=AutomationControlled"
    assert args.count("--disable-gpu") == 1
    assert "--disable-dev-shm-usage" in args and "--renderer-process-limit=2" in args
    assert free_tier.merge_args(None) == free_tier.LOW_MEMORY_ARGS


def test_patched_launch_passes_the_args(monkeypatch):
    from playwright.async_api._generated import BrowserType as AsyncBrowserType
    from playwright.sync_api._generated import BrowserType

    monkeypatch.setattr(AsyncBrowserType, "launch", AsyncBrowserType.launch)  # restored after the test
    seen = {}
    monkeypatch.setattr(BrowserType, "launch", lambda self, **kw: seen.update(kw) or "browser")
    free_tier.patch_chromium_launch()
    assert BrowserType.launch(object(), headless=True, args=["--x"]) == "browser"
    assert seen["headless"] is True and seen["args"][0] == "--x" and "--disable-gpu" in seen["args"]


def test_waits_get_longer(monkeypatch):
    from sandbox_verifier import verifier
    from scanner import navigator

    for module, name in [(navigator, "SETTLE_TIMEOUT_MS"), (verifier, "POPUP_OPEN_SECONDS"),
                         (verifier, "BUTTON_SETTLE_SECONDS"), (verifier, "NEXT_RETRY_SECONDS"),
                         (verifier, "BUTTON_WAIT_SECONDS"), (verifier, "SUCCESS_WAIT_SECONDS")]:
        monkeypatch.setattr(module, name, getattr(module, name))   # restored after the test
    before = verifier.POPUP_OPEN_SECONDS
    free_tier.slow_down_waits()
    assert verifier.POPUP_OPEN_SECONDS == before * free_tier.SLOW_FACTOR
    assert navigator.SETTLE_TIMEOUT_MS >= 24000 and verifier.SUCCESS_WAIT_SECONDS >= 120


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_store_runs_in_process_on_its_port():
    from demo_stores.serve import STORES_DIR

    port = _free_port()
    url = free_tier.start_store_in_process(STORES_DIR / "legacy_store", port)
    try:
        assert requests.get(f"{url}/health", timeout=5).json()["paypal_sdk"] == "v5"
        assert 'id="add-to-cart"' in requests.get(url, timeout=5).text
    finally:
        free_tier.stop_stores_in_process()


def test_heavy_jobs_run_one_at_a_time():
    running, peak = 0, 0

    async def job(_request):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return "done"

    async def main():
        free_tier._queue_lock = None
        return await asyncio.gather(*(free_tier.run_one_at_a_time(job, None) for _ in range(3)))

    assert asyncio.run(main()) == ["done"] * 3
    assert peak == 1
