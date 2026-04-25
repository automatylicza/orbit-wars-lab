"""Smoke integration tests for CLI via subprocess."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent.parent


def _cli(args: list[str], cwd: Path | None = None, env_runs: Path | None = None):
    cmd = [sys.executable, "-m", "orbit_wars_app.tournament", *args]
    env = None
    if env_runs is not None:
        env = os.environ.copy()
        env["ORBIT_WARS_RUNS_DIR"] = str(env_runs)
    return subprocess.run(
        cmd,
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def test_cli_list_shows_baselines():
    r = _cli(["list"])
    assert r.returncode == 0, f"stderr:\n{r.stderr}"
    assert "baselines/random" in r.stdout
    assert "baselines/nearest-sniper" in r.stdout
    assert "baselines/starter" in r.stdout


def test_cli_show_agent():
    r = _cli(["show", "baselines/nearest-sniper"])
    assert r.returncode == 0, f"stderr:\n{r.stderr}"
    assert "nearest-sniper" in r.stdout
    assert "Nearest Planet Sniper" in r.stdout  # display name from agent.yaml


def test_cli_show_missing_agent_nonzero_exit():
    r = _cli(["show", "nonexistent/agent"])
    assert r.returncode != 0
    assert "not found" in r.stderr.lower() or "not found" in r.stdout.lower()


def test_cli_run_pair_fast(tmp_path: Path):
    runs = tmp_path / "runs"
    runs.mkdir()
    r = _cli(
        [
            "run",
            "--agents", "baselines/random", "baselines/random",
            "--games-per-pair", "1",
            "--mode", "fast",
        ],
        env_runs=runs,
    )
    assert r.returncode == 0, f"stderr:\n{r.stderr}"
    # Sprawdź że run_dir został utworzony (pomiń 'latest' — to symlink)
    dirs = [p for p in runs.iterdir() if p.is_dir() and not p.is_symlink()]
    assert len(dirs) == 1
    assert (dirs[0] / "results.json").is_file()


def test_cli_head_to_head(tmp_path: Path):
    runs = tmp_path / "runs"
    runs.mkdir()
    r = _cli(
        [
            "head-to-head",
            "baselines/random",
            "baselines/nearest-sniper",
            "--games", "1",
            "--mode", "fast",
        ],
        env_runs=runs,
    )
    assert r.returncode == 0, f"stderr:\n{r.stderr}"
    run_dir = next(p for p in runs.iterdir() if p.is_dir())
    results = json.loads((run_dir / "results.json").read_text())
    assert len(results["matches"]) == 1
