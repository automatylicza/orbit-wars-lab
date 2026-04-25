"""Tests for orbit_wars_app.agent_serve.load_agent (import logic)."""
from __future__ import annotations

from pathlib import Path

import pytest

from orbit_wars_app.agent_serve import load_agent


FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_load_agent_ok():
    agent_fn = load_agent(str(FIXTURES / "agent_ok"))
    assert agent_fn is not None
    assert callable(agent_fn)
    # Empty-action agent
    assert agent_fn({"planets": [], "fleets": [], "player": 0}) == []


def test_load_agent_from_no_yaml_dir():
    agent_fn = load_agent(str(FIXTURES / "agent_no_yaml"))
    assert callable(agent_fn)


def test_load_agent_returns_none_for_missing_main_py(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    # Brak main.py — ale do load_agent podajemy nieistniejący plik
    with pytest.raises(FileNotFoundError):
        load_agent(str(tmp_path / "nonexistent"))


def test_load_agent_picks_last_callable(tmp_path: Path):
    """Kompatybilnie z kaggle-envs: jeśli w module jest kilka callable,
    bierzemy ostatni (ostatni = agent(), wcześniejsze = helpery)."""
    agent_dir = tmp_path / "multi"
    agent_dir.mkdir()
    (agent_dir / "main.py").write_text(
        "def helper():\n    pass\n\n"
        "def agent(obs):\n    return ['marker']\n"
    )
    agent_fn = load_agent(str(agent_dir))
    assert agent_fn({}) == ["marker"]
