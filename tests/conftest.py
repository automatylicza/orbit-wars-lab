"""Shared pytest fixtures."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_zoo(tmp_path: Path) -> Path:
    """Tmp directory with `agents/` skeleton. Tests populate it per-case."""
    zoo = tmp_path / "agents"
    (zoo / "baselines").mkdir(parents=True)
    (zoo / "external").mkdir(parents=True)
    (zoo / "mine").mkdir(parents=True)
    return zoo


@pytest.fixture
def tmp_runs(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    runs.mkdir()
    return runs


def copy_fixture_agent(fixture_name: str, dest: Path) -> Path:
    """Copy tests/fixtures/<fixture_name>/ into dest/<fixture_name>/."""
    src = FIXTURES_DIR / fixture_name
    target = dest / fixture_name
    shutil.copytree(src, target)
    return target
