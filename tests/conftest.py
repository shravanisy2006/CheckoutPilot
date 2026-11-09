"""
Shared test setup (pytest loads this file before any test file).

Tests must not depend on the developer's own .env (keys, flags). In particular, a local .env usually
has ALLOW_LOCALHOST_SCANS=true so the demo stores can be scanned, but the scanner's
security tests check the safe default (localhost blocked). We set the safe default here,
before the backend runs load_dotenv() (which never overrides a variable already set).
Tests that need localhost scans turn it on themselves with monkeypatch.setenv.
"""

import os

os.environ["ALLOW_LOCALHOST_SCANS"] = "false"

# Tests never call a real AI model for the code agent (no cost, same result on every machine).
# Tests that need an AI use a fake one. The real model is used by `run_demo.py` and the API.
os.environ["CODE_AGENT_PROVIDER"] = "deterministic"
