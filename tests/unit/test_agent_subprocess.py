"""Integration tests for spawn_agent / shutdown — real subprocesses."""
from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from orbit_wars_app.agent_subprocess import _agent_safe_env, spawn_agent, shutdown


FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_spawn_ok_agent_starts_server():
    handle = spawn_agent(FIXTURES / "agent_ok", agent_id="test/agent_ok")
    try:
        assert handle.url.startswith("http://127.0.0.1:")
        r = httpx.get(f"{handle.url}/health", timeout=5)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
    finally:
        shutdown(handle)


def test_spawn_respects_startup_timeout():
    with pytest.raises(RuntimeError) as exc_info:
        spawn_agent(FIXTURES / "does_not_exist", agent_id="fake/nope")
    assert "failed" in str(exc_info.value).lower() or "exit" in str(exc_info.value).lower()


def test_shutdown_terminates_subprocess():
    handle = spawn_agent(FIXTURES / "agent_ok", agent_id="test/agent_ok")
    pid = handle.proc.pid

    shutdown(handle)

    time.sleep(0.2)
    assert handle.proc.poll() is not None, "Subprocess should have exited"


def test_spawn_two_agents_different_ports():
    h1 = spawn_agent(FIXTURES / "agent_ok", agent_id="test/a1")
    h2 = spawn_agent(FIXTURES / "agent_ok", agent_id="test/a2")
    try:
        assert h1.url != h2.url
    finally:
        shutdown(h1)
        shutdown(h2)


# ---------- _agent_safe_env: keep Kaggle credentials out of forked agents ----------


def test_agent_safe_env_strips_kaggle_api_token(monkeypatch):
    """Agent code (especially `agents/external/*` from competitor notebooks)
    must not see KAGGLE_API_TOKEN — they could exfiltrate it with one HTTP call."""
    monkeypatch.setenv("KAGGLE_API_TOKEN", "KGAT_secret")
    env = _agent_safe_env()
    assert "KAGGLE_API_TOKEN" not in env


def test_agent_safe_env_strips_kaggle_username_and_key(monkeypatch):
    """Same reasoning for legacy creds — KAGGLE_USERNAME + KAGGLE_KEY would
    let any agent log in to Kaggle as the user."""
    monkeypatch.setenv("KAGGLE_USERNAME", "alice")
    monkeypatch.setenv("KAGGLE_KEY", "secret_key")
    env = _agent_safe_env()
    assert "KAGGLE_USERNAME" not in env
    assert "KAGGLE_KEY" not in env


def test_agent_safe_env_preserves_path_and_home(monkeypatch):
    """Don't strip too aggressively — agents need PATH to find python and
    HOME to import packages from site-packages."""
    monkeypatch.setenv("KAGGLE_API_TOKEN", "KGAT_secret")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOME", "/home/test")
    env = _agent_safe_env()
    assert env.get("PATH") == "/usr/bin:/bin"
    assert env.get("HOME") == "/home/test"


def test_agent_safe_env_strips_arbitrary_kaggle_prefix(monkeypatch):
    """Future Kaggle env vars (e.g. KAGGLE_CONFIG_DIR pointing to a token
    file) shouldn't slip through — anything starting with KAGGLE_ goes."""
    monkeypatch.setenv("KAGGLE_FUTURE_VAR", "leak_me")
    env = _agent_safe_env()
    assert "KAGGLE_FUTURE_VAR" not in env


def test_agent_responds_to_act_endpoint():
    handle = spawn_agent(FIXTURES / "agent_ok", agent_id="test/agent_ok")
    try:
        r = httpx.post(
            f"{handle.url}/act",
            json={
                "action": "act",
                "configuration": {"episodeSteps": 500, "actTimeout": 1},
                "state": {"observation": {"planets": [], "fleets": [], "player": 0}},
            },
            timeout=5,
        )
        assert r.status_code == 200
        assert r.json() == {"action": []}
    finally:
        shutdown(handle)


def test_agent_exception_returns_base_exception_envelope():
    """Agent raising RuntimeError returns {'action': 'BaseException::RuntimeError: <msg>'}."""
    handle = spawn_agent(FIXTURES / "agent_raises", agent_id="test/raises")
    try:
        r = httpx.post(
            f"{handle.url}/act",
            json={
                "action": "act",
                "configuration": {},
                "state": {"observation": {"planets": [], "fleets": [], "player": 0}},
            },
            timeout=5,
        )
        assert r.status_code == 200
        action = r.json()["action"]
        assert isinstance(action, str)
        assert action.startswith("BaseException::RuntimeError:")
        assert "boom" in action
    finally:
        shutdown(handle)
