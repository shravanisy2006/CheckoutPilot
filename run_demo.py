"""
Start the whole CheckoutPilot demo with one command (Windows, macOS, Linux).

    python run_demo.py              # real mode: uses your .env (PayPal Sandbox + Gemini keys)
    python run_demo.py --mock       # no keys needed: fake PayPal + fake verifier, AI rules only
    python run_demo.py --check      # only check your setup, start nothing
    python run_demo.py --smoke-test # start everything, run one real scan, then stop

It starts:
    legacy demo store     http://localhost:8101   (PayPal SDK v5, the "before")
    upgraded demo store   http://localhost:8102   (PayPal SDK v6, the "after")
    backend API           http://localhost:8000/docs
    dashboard             http://localhost:5173   (needs Node.js 18+)

Press Ctrl+C to stop everything.
"""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend-react"
BACKEND_PORT = 8000
DASHBOARD_PORT = 5173
DASHBOARD_ORIGINS = [f"http://localhost:{DASHBOARD_PORT}", f"http://127.0.0.1:{DASHBOARD_PORT}"]
IS_WINDOWS = os.name == "nt"


# ------------------------------------------------------------------- setup ---
def say(message: str = "") -> None:
    print(message, flush=True)


def load_env_file() -> dict:
    """Read .env (create it from .env.example if missing)."""
    env_file, example = ROOT / ".env", ROOT / ".env.example"
    if not env_file.exists() and example.exists():
        shutil.copyfile(example, env_file)
        say("Created .env from .env.example (fill in your keys, or use --mock).")
    from dotenv import dotenv_values
    return {k: v for k, v in dotenv_values(env_file).items() if v is not None} if env_file.exists() else {}


def is_placeholder(value: str | None) -> bool:
    value = (value or "").strip()
    return not value or value.startswith("your-") or value.endswith("@example.com")


def check_setup(env: dict, mock: bool) -> bool:
    """Print a checklist. Returns False if something blocks the demo."""
    ok = True
    say("Setup check")

    def line(passed: bool, text: str, fix: str = "", blocking: bool = True) -> None:
        nonlocal ok
        mark = "OK " if passed else ("!! " if blocking else "-- ")
        say(f"  {mark} {text}" + ("" if passed or not fix else f"\n        -> {fix}"))
        if not passed and blocking:
            ok = False

    line(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]} (3.10+ needed)", "Install Python 3.10 or newer")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser_ok = Path(p.chromium.executable_path).exists()
    except Exception:
        browser_ok = False
    line(browser_ok, "Playwright Chromium (for scanning and verifying)", "Run: playwright install chromium")
    npm = shutil.which("npm")
    line(bool(npm), "Node.js / npm (for the dashboard)", "Install Node.js 18+ from nodejs.org, or use --no-dashboard",
         blocking=False)

    if mock:
        say("  OK  Mock mode: PayPal and the Sandbox verifier are simulated; AI uses rule checks only")
    else:
        line(not is_placeholder(env.get("PAYPAL_CLIENT_ID")) and not is_placeholder(env.get("PAYPAL_CLIENT_SECRET")),
             "PayPal Sandbox keys in .env", "Set PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET, or use --mock")
        line(not is_placeholder(env.get("PAYPAL_SANDBOX_BUYER_EMAIL")),
             "Sandbox buyer account in .env (US Personal)",
             "Set PAYPAL_SANDBOX_BUYER_EMAIL / _PASSWORD, or use --mock", blocking=False)
        provider = (env.get("AI_PROVIDER") or "gemini").lower()
        key_var = {"gemini": "GOOGLE_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}.get(
            provider, "GOOGLE_API_KEY")
        line(not is_placeholder(env.get(key_var)), f"AI key {key_var} (for vision)",
             "Without it the AI uses rule checks only (still works)", blocking=False)
    return ok


def child_env(env: dict, mock: bool) -> dict:
    """Environment for every process we start."""
    merged = {**os.environ, **env}
    merged["PYTHONPATH"] = str(ROOT) + os.pathsep + merged.get("PYTHONPATH", "")
    merged["ALLOW_LOCALHOST_SCANS"] = "true"  # the demo stores run on localhost
    origins = [o.strip() for o in merged.get("CORS_ORIGINS", "").split(",") if o.strip()]
    merged["CORS_ORIGINS"] = ",".join(dict.fromkeys(origins + DASHBOARD_ORIGINS))
    merged["VITE_API_BASE_URL"] = f"http://localhost:{BACKEND_PORT}"
    if mock:
        merged.update(MOCK_PAYPAL="true", MOCK_VERIFIER="true", AI_VISION_ENABLED="false")
    return merged


# --------------------------------------------------------------- processes ---
def wait_for(url: str, seconds: float, proc: subprocess.Popen | None = None) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            if requests.get(url, timeout=2).status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def stop(proc: subprocess.Popen) -> None:
    """Stop a process and everything it started (npm starts node, for example)."""
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def start(command: list[str], cwd: Path, env: dict, log_name: str) -> subprocess.Popen:
    logs = ROOT / "outputs" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = open(logs / f"{log_name}.log", "w", encoding="utf-8")
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WINDOWS else {"start_new_session": True}
    return subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, **kwargs)


def port_in_use(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def stop_old_command(ports: list[int]) -> str:
    """The command that stops whatever is still listening on these ports."""
    if IS_WINDOWS:
        return ("Get-NetTCPConnection -State Listen -LocalPort " + ",".join(map(str, ports))
                + " | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }")
    return "kill $(lsof -t " + " ".join(f"-i:{p}" for p in ports) + ")"


def check_ports_free(dashboard: bool) -> None:
    """An older CheckoutPilot still running would serve OLD code: stop instead of reusing it."""
    from demo_stores.serve import KNOWN_STORES
    ports = [KNOWN_STORES["legacy"][1], KNOWN_STORES["upgraded"][1], BACKEND_PORT] + ([DASHBOARD_PORT] if dashboard else [])
    busy = [p for p in ports if port_in_use(p)]
    if busy:
        raise RuntimeError(
            f"Port(s) {', '.join(map(str, busy))} are already in use, probably by an earlier CheckoutPilot that is "
            "still running (it would run old code).\n"
            "       Close the other terminal running it, or stop it with this command, then try again:\n"
            f"       {stop_old_command(busy)}")


def start_everything(env: dict, dashboard: bool) -> list[tuple[str, subprocess.Popen]]:
    from demo_stores.serve import KNOWN_STORES, _build_command
    check_ports_free(dashboard)
    started = []
    for name in ("legacy", "upgraded"):
        folder, port = KNOWN_STORES[name]
        url = f"http://localhost:{port}"
        proc = start(_build_command(ROOT / "demo_stores" / folder, port), ROOT, env, f"store_{name}")
        if not wait_for(f"{url}/health", 25, proc):
            raise RuntimeError(f"The {name} store did not start (see outputs/logs/store_{name}.log). Is port {port} free?")
        started.append((f"{name} store", proc))
        say(f"  {name + ' store':<17} {url}")

    proc = start([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(BACKEND_PORT)],
                 ROOT, env, "backend")
    if not wait_for(f"http://localhost:{BACKEND_PORT}/api/health", 40, proc):
        raise RuntimeError("The backend did not start (see outputs/logs/backend.log). Is port 8000 free?")
    started.append(("backend", proc))
    say(f"  backend API       http://localhost:{BACKEND_PORT}/docs")

    npm = shutil.which("npm")
    if dashboard and npm:
        if not (FRONTEND / "node_modules").exists():
            say("  installing dashboard packages (first run only, 1-5 minutes) ...")
            subprocess.run([npm, "install", "--no-audit", "--no-fund", "--legacy-peer-deps"], cwd=FRONTEND,
                           env=env, check=True)
        proc = start([npm, "run", "dev", "--", "--port", str(DASHBOARD_PORT), "--strictPort"], FRONTEND, env,
                     "dashboard")
        if not wait_for(f"http://localhost:{DASHBOARD_PORT}/", 90, proc):
            raise RuntimeError("The dashboard did not start (see outputs/logs/dashboard.log).")
        started.append(("dashboard", proc))
        say(f"  dashboard         http://localhost:{DASHBOARD_PORT}   <- open this")
    elif dashboard:
        say("  dashboard         skipped (Node.js not found)")
    return started


def smoke_test() -> bool:
    """One real scan of the legacy store through the API."""
    say("\nSmoke test: scanning the legacy store through the API ...")
    response = requests.post(f"http://localhost:{BACKEND_PORT}/api/scan",
                             json={"store_url": "http://localhost:8101"}, timeout=180)
    body = response.json()
    issues = body.get("issues") or body.get("gaps") or []
    say(f"  HTTP {response.status_code} | status {body.get('status')} | health {body.get('health_score')} "
        f"| {len(issues)} issue(s)")
    return response.status_code == 200 and body.get("status") == "completed" and len(issues) >= 3


# -------------------------------------------------------------------- main ---
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the CheckoutPilot demo.")
    parser.add_argument("--mock", action="store_true", help="no keys needed (simulated PayPal and verifier)")
    parser.add_argument("--check", action="store_true", help="only check the setup")
    parser.add_argument("--no-dashboard", action="store_true", help="do not start the React dashboard")
    parser.add_argument("--smoke-test", action="store_true", help="start, run one scan, stop")
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    env_file = load_env_file()
    ready = check_setup(env_file, args.mock)
    if args.check:
        return 0 if ready else 1
    if not ready:
        say("\nFix the items marked !! above (or run with --mock), then try again.")
        return 1

    env = child_env(env_file, args.mock)
    say("\nStarting CheckoutPilot" + (" (mock mode)" if args.mock else "") + " ...")
    started: list[tuple[str, subprocess.Popen]] = []
    try:
        started = start_everything(env, dashboard=not args.no_dashboard and not args.smoke_test)
        if args.smoke_test:
            return 0 if smoke_test() else 1
        say("\nReady. In the dashboard: Audit -> enter http://localhost:8101 -> Start scan.")
        say("Logs: outputs/logs/   Stop: Ctrl+C")
        while all(proc.poll() is None for _, proc in started):
            time.sleep(1)
        crashed = [name for name, proc in started if proc.poll() is not None]
        say(f"\nStopped because {', '.join(crashed)} exited (see outputs/logs/).")
        return 1
    except KeyboardInterrupt:
        say("\nStopping ...")
        return 0
    except RuntimeError as error:
        say(f"\nERROR: {error}")
        return 1
    finally:
        for _, proc in reversed(started):
            stop(proc)


if __name__ == "__main__":
    sys.exit(main())
