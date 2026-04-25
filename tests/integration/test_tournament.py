"""Integration: tournament runner orchestrating multiple matches."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orbit_wars_app.schemas import TournamentConfig
from orbit_wars_app.tournament import Tournament


PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def isolated_runs_dir(tmp_path: Path):
    runs = tmp_path / "runs"
    runs.mkdir()
    return runs


def test_tournament_one_pair_one_game_fast(isolated_runs_dir: Path):
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/nearest-sniper"],
        games_per_pair=1,
        mode="fast",
        format="2p",
        parallel=1,
        seed_base=42,
    )
    t = Tournament(
        config=cfg,
        runs_root=isolated_runs_dir,
        zoo_root=PROJECT_ROOT / "agents",
    )
    run_id = t.run()

    run_dir = isolated_runs_dir / run_id
    assert run_dir.is_dir()
    assert (run_dir / "config.json").is_file()
    assert (run_dir / "results.json").is_file()
    assert (run_dir / "trueskill.json").is_file()

    results = json.loads((run_dir / "results.json").read_text())
    assert len(results["matches"]) == 1
    assert results["summary"]["total_matches"] == 1

    # Replay present
    replays = list((run_dir / "replays").glob("*.json"))
    assert len(replays) == 1


def test_tournament_three_agents_k3_round_robin_fast(isolated_runs_dir: Path):
    cfg = TournamentConfig(
        agents=[
            "baselines/random",
            "baselines/starter",
            "baselines/nearest-sniper",
        ],
        games_per_pair=3,
        mode="fast",
        format="2p",
    )
    t = Tournament(
        config=cfg,
        runs_root=isolated_runs_dir,
        zoo_root=PROJECT_ROOT / "agents",
    )
    run_id = t.run()

    results = json.loads((isolated_runs_dir / run_id / "results.json").read_text())
    # 3 agents = C(3,2) = 3 pairs, K=3 games → 9 matches
    assert results["summary"]["total_matches"] == 9


def test_tournament_updates_persistent_trueskill(isolated_runs_dir: Path):
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/nearest-sniper"],
        games_per_pair=2,
        mode="fast",
    )
    t = Tournament(
        config=cfg,
        runs_root=isolated_runs_dir,
        zoo_root=PROJECT_ROOT / "agents",
    )
    t.run()

    persistent = isolated_runs_dir / "trueskill.json"
    assert persistent.is_file()
    data = json.loads(persistent.read_text())
    assert "baselines/random" in data["ratings"]
    assert "baselines/nearest-sniper" in data["ratings"]
    assert data["ratings"]["baselines/random"]["2p"]["games_played"] == 2


def test_tournament_second_run_accumulates_ratings(isolated_runs_dir: Path):
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/nearest-sniper"],
        games_per_pair=1,
        mode="fast",
    )
    t1 = Tournament(config=cfg, runs_root=isolated_runs_dir, zoo_root=PROJECT_ROOT / "agents")
    t1.run()

    t2 = Tournament(config=cfg, runs_root=isolated_runs_dir, zoo_root=PROJECT_ROOT / "agents")
    t2.run()

    persistent = json.loads((isolated_runs_dir / "trueskill.json").read_text())
    assert persistent["ratings"]["baselines/random"]["2p"]["games_played"] == 2
