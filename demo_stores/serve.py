"""
Start and stop demo stores (any store folder, including an AI-patched copy).

Command line (from the project root):
    python -m demo_stores.serve legacy              -> http://localhost:8101
    python -m demo_stores.serve legacy --port 9000
    python -m demo_stores.serve path/to/patched_store --port 8103

From Python (used by the backend / sandbox verifier):
    from demo_stores.serve import start_store, stop_store
    url = start_store("demo_stores/legacy_store", 8101)
    ...
    stop_store(8101)

Every store folder must contain app.py with a FastAPI object called `app`
and a GET /health route.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORES_DIR = Path(__file__).resolve().parent

# Short names you can type instead of a folder path.
KNOWN_STORES = {
    "legacy": ("legacy_store", 8101),
    "upgraded": ("upgraded_store", 8102),
}

HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 20

_running: dict[int, subprocess.Popen] = {}


class StoreError(Exception):
    """Raised when a store cannot be found or does not start."""


def resolve_store(name_or_path: str) -> tuple[Path, int | None]:
    """Turn 'legacy' or a folder path into (store folder, default port or None)."""
    if name_or_path in KNOWN_STORES:
        folder, port = KNOWN_STORES[name_or_path]
        return STORES_DIR / folder, port
    return Path(name_or_path).resolve(), None


def _build_command(store_dir: Path, port: int) -> list[str]:
    return [
        sys.executable, "-m", "uvicorn", "app:app",
        "--app-dir", str(store_dir),
        "--host", HOST, "--port", str(port),
        "--log-level", "warning",
    ]


def _environment() -> dict:
    """Let the store import project packages such as paypal_integration."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(PROJECT_ROOT) + (os.pathsep + existing if existing else "")
    return env


def _check_store_dir(store_dir: Path) -> None:
    if not (store_dir / "app.py").is_file():
        raise StoreError(f"No app.py found in {store_dir}")


def wait_until_healthy(url: str, process: subprocess.Popen | None = None,
                       timeout: float = STARTUP_TIMEOUT_SECONDS) -> None:
    """Poll <url>/health until it answers, the process dies, or time runs out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise StoreError(f"Store process exited early (code {process.returncode}). "
                             "Is the port already in use?")
        try:
            if requests.get(f"{url}/health", timeout=1).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.3)
    raise StoreError(f"Store at {url} did not become healthy within {timeout:.0f}s")


def start_store(store_dir: str | Path, port: int) -> str:
    """Start the store in a background process and return its URL once /health answers."""
    store_dir = Path(store_dir).resolve()
    _check_store_dir(store_dir)
    if port in _running and _running[port].poll() is None:
        raise StoreError(f"A store is already running on port {port}")

    process = subprocess.Popen(_build_command(store_dir, port), cwd=PROJECT_ROOT, env=_environment())
    url = f"http://localhost:{port}"
    try:
        wait_until_healthy(url, process)
    except StoreError:
        _terminate(process)
        raise
    _running[port] = process
    return url


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def stop_store(port: int) -> bool:
    """Stop the store started on this port. Returns False if none was running."""
    process = _running.pop(port, None)
    if process is None:
        return False
    _terminate(process)
    return True


def stop_all() -> None:
    for port in list(_running):
        stop_store(port)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a CheckoutPilot demo store.")
    parser.add_argument("store", help="'legacy', 'upgraded', or a path to a store folder")
    parser.add_argument("--port", type=int, help="port to use (default: 8101 legacy, 8102 upgraded)")
    args = parser.parse_args(argv)

    store_dir, default_port = resolve_store(args.store)
    port = args.port or default_port
    if port is None:
        parser.error("--port is required when you pass a folder path")
    try:
        _check_store_dir(store_dir)
    except StoreError as error:
        print(f"Error: {error}")
        return 1

    print(f"Serving {store_dir.name} at http://localhost:{port}  (Ctrl+C to stop)")
    try:
        return subprocess.call(_build_command(store_dir, port), cwd=PROJECT_ROOT, env=_environment())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
