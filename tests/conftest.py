"""
Shared test setup (pytest loads this file before any test file).

Tests must not depend on the developer's own .env. In particular, a local .env usually
has ALLOW_LOCALHOST_SCANS=true so the demo stores can be scanned, but the scanner's
security tests check the safe default (localhost blocked). We set the safe default here,
before the backend runs load_dotenv() (which never overrides a variable already set).
Tests that need localhost scans turn it on themselves with monkeypatch.setenv.
"""

import os

os.environ["ALLOW_LOCALHOST_SCANS"] = "false"
