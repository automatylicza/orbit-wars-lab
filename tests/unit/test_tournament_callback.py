"""Test tournament callback + run.json lifecycle."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orbit_wars_app.schemas import TournamentConfig
from orbit_wars_app.tournament import Tournament


PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_tournament_writes_run_json_with_lifecycle(tmp_path: Path):
    runs = tmp_path / "runs"
    runs.mkdir()
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/random"],
        games_per_pair=1,
        mode="fast",
    )
    t = Tournament(config=cfg, runs_root=runs, zoo_root=PROJECT_ROOT / "agents")

    run_id = t.run()

    run_json = runs / run_id / "run.json"
    assert run_json.is_file()
    data = json.loads(run_json.read_text())
    assert data["id"] == run_id
    assert data["status"] == "completed"
    assert data["total_matches"] == 1
    assert data["matches_done"] == 1
    assert "started_at" in data
    assert "finished_at" in data


def test_tournament_on_match_done_called_per_match(tmp_path: Path):
    runs = tmp_path / "runs"
    runs.mkdir()
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/random", "baselines/starter"],
        games_per_pair=2,
        mode="fast",
    )
    t = Tournament(config=cfg, runs_root=runs, zoo_root=PROJECT_ROOT / "agents")

    seen: list[tuple[int, int]] = []
    def cb(match_result, done: int, total: int) -> None:
        seen.append((done, total))

    t.run(on_match_done=cb)

    # 3 agents → C(3,2) = 3 pairs × K=2 = 6 matches
    assert len(seen) == 6
    # done counter should go 1..6, total constant 6
    assert [s[0] for s in seen] == [1, 2, 3, 4, 5, 6]
    assert all(s[1] == 6 for s in seen)
