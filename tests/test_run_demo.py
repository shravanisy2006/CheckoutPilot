"""Tests for run_demo.py helpers (nothing is started). The full launch is checked with
`python run_demo.py --mock --smoke-test`."""

import run_demo


def test_placeholders_are_detected():
    assert run_demo.is_placeholder("your-sandbox-client-id-here")
    assert run_demo.is_placeholder("buyer-sandbox-email@example.com")
    assert run_demo.is_placeholder("")
    assert not run_demo.is_placeholder("sb-abc123@personal.example.com")
    assert not run_demo.is_placeholder("AbCdEf123")


def test_child_env_allows_dashboard_and_localhost():
    env = run_demo.child_env({"CORS_ORIGINS": "http://localhost:8501"}, mock=False)
    origins = env["CORS_ORIGINS"].split(",")
    assert "http://localhost:8501" in origins and "http://localhost:5173" in origins
    assert len(origins) == len(set(origins))
    assert env["ALLOW_LOCALHOST_SCANS"] == "true"
    assert env["VITE_API_BASE_URL"] == "http://localhost:8000"
    assert env.get("MOCK_PAYPAL") != "true"


def test_mock_mode_needs_no_keys():
    env = run_demo.child_env({}, mock=True)
    assert env["MOCK_PAYPAL"] == "true" and env["MOCK_VERIFIER"] == "true"
    assert env["AI_VISION_ENABLED"] == "false"
    assert run_demo.check_setup({}, mock=True) in (True, False)  # never raises without keys


def test_refuses_to_reuse_an_old_running_copy(monkeypatch):
    """Seen live: an old backend kept port 8000, so the new one exited and old code kept serving."""
    import pytest
    import run_demo
    monkeypatch.setattr(run_demo, "port_in_use", lambda port: port == 8000)
    with pytest.raises(RuntimeError) as error:
        run_demo.check_ports_free(dashboard=True)
    assert "8000" in str(error.value) and "already in use" in str(error.value)


def test_stop_command_names_the_busy_ports(monkeypatch):
    import run_demo
    monkeypatch.setattr(run_demo, "IS_WINDOWS", True)
    assert "-LocalPort 8000,8101" in run_demo.stop_old_command([8000, 8101])
    monkeypatch.setattr(run_demo, "IS_WINDOWS", False)
    assert run_demo.stop_old_command([8000]) == "kill $(lsof -t -i:8000)"
