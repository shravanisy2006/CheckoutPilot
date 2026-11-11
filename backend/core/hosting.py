"""
Settings for running CheckoutPilot as one hosted web service (Render, see render.yaml).

Everything here is OFF unless its environment variable is set, so local development
(`python run_demo.py`) works exactly as before.

    START_DEMO_STORES=true      start the two example stores inside the service (8101, 8102)
    DASHBOARD_DIR=<folder>      serve the built dashboard (dist/client) from the same URL
    RATE_LIMIT_PER_HOUR=30      max heavy requests (scan / fix / verify / re-scan) per visitor per hour
    OUTPUTS_MAX_AGE_HOURS=24    delete screenshots and patched copies older than this
    ASYNC_JOBS=true             long steps answer with a job id the dashboard polls (see jobs.py)
    FREE_TIER=true              fit into a 512 MB free plan (see free_tier.py)
"""

import os
import shutil
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.core import free_tier, jobs


def _int_env(name: str, default: int = 0) -> int:
    try:
        return max(int(os.getenv(name, str(default)).strip()), 0)
    except ValueError:
        return default


def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes")


def api_servers() -> list[dict]:
    """OpenAPI 'servers': the public URL first when hosted (RENDER_EXTERNAL_URL is set by Render)."""
    servers = [{"url": "http://localhost:8000", "description": "Local CheckoutPilot backend"}]
    public = (os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if public:
        servers.insert(0, {"url": public, "description": "Hosted CheckoutPilot (Render)"})
    return servers


# ------------------------------------------------------------ demo stores ---
def start_demo_stores() -> list[str]:
    """Start the example stores (the 'before' and 'after' Inkwell & Co.) if asked to."""
    if not _flag("START_DEMO_STORES"):
        return []
    from demo_stores.serve import KNOWN_STORES, STORES_DIR, start_store

    start = free_tier.start_store_in_process if free_tier.enabled() else start_store
    return [start(STORES_DIR / folder, port) for folder, port in KNOWN_STORES.values()]


def stop_demo_stores() -> None:
    from demo_stores.serve import stop_all

    stop_all()
    free_tier.stop_stores_in_process()


# ------------------------------------------------------------ rate limit ---
HEAVY_PREFIXES = ("/api/scan", "/api/fix", "/api/verify")


def is_heavy(method: str, path: str) -> bool:
    """POSTs that start a browser or a model. Reading results is never limited."""
    return method == "POST" and path.startswith(HEAVY_PREFIXES)


def client_ip(request: Request) -> str:
    """The visitor's address. Render (and most hosts) put it first in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded.strip():
        return strip_port(forwarded.split(",")[0].strip())
    return request.client.host if request.client else "unknown"


def strip_port(address: str) -> str:
    """Azure sends '1.2.3.4:56789'; the port changes on every request, the visitor does not."""
    if address.startswith("[") and "]" in address:          # [IPv6]:port
        return address[1:address.index("]")]
    if address.count(":") == 1:                               # IPv4:port
        return address.split(":")[0]
    return address                                            # IPv4 or bare IPv6


class RateLimiter:
    """At most `limit` heavy requests per visitor in any `window` seconds (in memory)."""

    def __init__(self, limit: int, window: float = 3600.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """(allowed, seconds until the next request is allowed)."""
        if self.limit <= 0:
            return True, 0
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, int(self.window - (now - hits[0])) + 1
            hits.append(now)
            return True, 0


limiter = RateLimiter(_int_env("RATE_LIMIT_PER_HOUR"))


# --------------------------------------------------------- old outputs ---
OUTPUT_SUBDIRS = ("scans", "patched", "verifications", "fixes", "rescans")
_last_prune = 0.0


def prune_outputs(root: Path, max_age_hours: int, now: float | None = None) -> int:
    """Delete run folders under outputs/<kind>/ older than max_age_hours. Returns how many."""
    if max_age_hours <= 0:
        return 0
    now = time.time() if now is None else now
    removed = 0
    for kind in OUTPUT_SUBDIRS:
        base = root / kind
        if not base.is_dir():
            continue
        for item in base.iterdir():
            try:
                if now - item.stat().st_mtime > max_age_hours * 3600:
                    shutil.rmtree(item) if item.is_dir() else item.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def maybe_prune(root: Path) -> None:
    """Prune at most every 10 minutes (called before heavy requests)."""
    global _last_prune
    if time.monotonic() - _last_prune < 600:
        return
    _last_prune = time.monotonic()
    prune_outputs(root, _int_env("OUTPUTS_MAX_AGE_HOURS"))


def make_middleware(outputs_dir: Path):
    async def hosting_middleware(request: Request, call_next):
        if is_heavy(request.method, request.url.path):
            if jobs.is_internal(request):          # a job running its own step: already counted
                return await _run(call_next, request)
            allowed, wait = limiter.allow(client_ip(request))
            if not allowed:
                minutes = max(1, round(wait / 60))
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(wait)},
                    content={"detail": f"This public demo allows {limiter.limit} scans/fixes/proofs per hour. "
                                       f"Please try again in about {minutes} min, or use Demo mode."},
                )
            maybe_prune(outputs_dir)
            if jobs.enabled():
                return await jobs.start(request)
            return await _run(call_next, request)
        return await call_next(request)

    return hosting_middleware


async def _run(call_next, request: Request):
    """Run a heavy step; on a small free plan, one at a time (two browsers never share 512 MB)."""
    if free_tier.enabled():
        return await free_tier.run_one_at_a_time(call_next, request)
    return await call_next(request)


# -------------------------------------------------------------- dashboard ---
def dashboard_dir() -> Path | None:
    """The built dashboard folder, if DASHBOARD_DIR points at one (it must hold _shell.html)."""
    value = os.getenv("DASHBOARD_DIR", "").strip()
    if not value:
        return None
    folder = Path(value).resolve()
    return folder if (folder / "_shell.html").is_file() else None


def dashboard_response(folder: Path, path: str) -> Response:
    """A real file (JS, CSS, images), the pre-drawn page for this route, or the app shell."""
    if path.startswith(("api/", "files/")) or path in ("api", "files", "docs", "openapi.json"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    clean = path.strip("/")
    # The file itself (assets), then the page pre-drawn for this route (audit.html or audit/index.html).
    for name in ([clean, f"{clean}.html", f"{clean}/index.html"] if clean else ["index.html"]):
        candidate = (folder / name).resolve()
        if candidate.is_relative_to(folder) and candidate.is_file():
            return FileResponse(candidate)
    return FileResponse(folder / "_shell.html", media_type="text/html")
