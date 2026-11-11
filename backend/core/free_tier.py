"""
FREE_TIER=true: fit the whole app into Render's free web service (512 MB memory, 0.1 CPU).

Nothing about what CheckoutPilot does changes; only how it uses the small machine:
  * the two example stores run inside the backend process (saves ~100 MB vs. two processes),
  * Chromium starts with low-memory switches,
  * only one browser job (scan / fix / proof / re-scan) runs at a time; others wait their turn,
  * waits are longer, because the CPU is about 10x slower than a laptop.

Off by default: local development is unchanged.
"""

import asyncio
import importlib.util
import os
import threading
import time
from pathlib import Path

import requests

LOW_MEMORY_ARGS = [
    "--disable-dev-shm-usage",          # /dev/shm is tiny in containers
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-sync",
    "--mute-audio",
    "--no-first-run",
    "--renderer-process-limit=2",
]
SLOW_FACTOR = 3        # multiply the scanner's and verifier's short waits by this
QUEUE_WAIT_SECONDS = 300

_queue_lock: asyncio.Lock | None = None


def enabled() -> bool:
    return os.getenv("FREE_TIER", "false").strip().lower() in ("1", "true", "yes")


# ------------------------------------------------------------- Chromium ---
def merge_args(args) -> list[str]:
    merged = list(args or [])
    merged += [a for a in LOW_MEMORY_ARGS if a not in merged]
    return merged


def patch_chromium_launch() -> None:
    """Every chromium.launch(...) in the project gets the low-memory switches."""
    from playwright.async_api._generated import BrowserType as AsyncBrowserType
    from playwright.sync_api._generated import BrowserType as SyncBrowserType

    for cls in (SyncBrowserType, AsyncBrowserType):
        original = cls.launch
        if getattr(original, "_cp_low_memory", False):
            continue

        def launch(self, *a, _original=original, **kw):
            kw["args"] = merge_args(kw.get("args"))
            return _original(self, *a, **kw)

        launch._cp_low_memory = True
        cls.launch = launch


def slow_down_waits() -> None:
    """Longer short-waits for a slow CPU (the long ones are already generous)."""
    from sandbox_verifier import verifier
    from scanner import navigator

    navigator.SETTLE_TIMEOUT_MS = max(navigator.SETTLE_TIMEOUT_MS, 8000 * SLOW_FACTOR)
    for name in ("POPUP_OPEN_SECONDS", "BUTTON_SETTLE_SECONDS", "NEXT_RETRY_SECONDS"):
        setattr(verifier, name, getattr(verifier, name) * SLOW_FACTOR)
    verifier.BUTTON_WAIT_SECONDS = max(verifier.BUTTON_WAIT_SECONDS, 90)
    verifier.SUCCESS_WAIT_SECONDS = max(verifier.SUCCESS_WAIT_SECONDS, 120)


def apply() -> bool:
    """Called once at startup. Returns True when free-tier mode is on."""
    if not enabled():
        return False
    patch_chromium_launch()
    slow_down_waits()
    return True


# --------------------------------------------------- stores in-process ---
_servers: list = []


def _load_store_app(folder: Path):
    spec = importlib.util.spec_from_file_location(f"cp_store_{folder.name}", folder / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


def start_store_in_process(folder: Path, port: int, timeout: float = 60) -> str:
    """Run a store on 127.0.0.1:<port> in a thread of this process (same URL as a separate process)."""
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(_load_store_app(folder), host="127.0.0.1", port=port,
                                           log_level="warning", lifespan="off"))
    server.install_signal_handlers = lambda: None   # the main server handles Ctrl+C / SIGTERM
    threading.Thread(target=server.run, name=f"store-{port}", daemon=True).start()
    _servers.append(server)
    url = f"http://localhost:{port}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{url}/health", timeout=2).status_code == 200:
                return url
        except requests.RequestException:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"Store {folder.name} did not start on port {port}")


def stop_stores_in_process() -> None:
    for server in _servers:
        server.should_exit = True
    _servers.clear()


# ----------------------------------------------------- one job at a time ---
async def run_one_at_a_time(call_next, request):
    """Heavy requests wait for each other, so two browsers never share 512 MB."""
    global _queue_lock
    if _queue_lock is None:
        _queue_lock = asyncio.Lock()
    try:
        await asyncio.wait_for(_queue_lock.acquire(), timeout=QUEUE_WAIT_SECONDS)
    except asyncio.TimeoutError:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, headers={"Retry-After": "60"}, content={
            "detail": "The free demo server is busy with another visitor's scan or proof. "
                      "Please try again in a minute, or use Demo mode."})
    try:
        return await call_next(request)
    finally:
        _queue_lock.release()
