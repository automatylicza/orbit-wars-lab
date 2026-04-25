"""Test że Tournament z is_quick_match=True propaguje do run.json."""
from __future__ import annotations

import json
from pathlib import Path

from orbit_wars_app.schemas import TournamentConfig
from orbit_wars_app.tournament import Tournament


PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_tournament_writes_is_quick_match_true(tmp_path: Path):
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/random"],
        games_per_pair=1,
        mode="fast",
        is_quick_match=True,
    )
    run_id = Tournament(
        config=cfg,
        runs_root=tmp_path,
        zoo_root=PROJECT_ROOT / "agents",
    ).run()
    run_json = json.loads((tmp_path / run_id / "run.json").read_text())
    assert run_json["is_quick_match"] is True


def test_tournament_writes_is_quick_match_false_by_default(tmp_path: Path):
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/random"],
        games_per_pair=1,
        mode="fast",
    )
    run_id = Tournament(
        config=cfg,
        runs_root=tmp_path,
        zoo_root=PROJECT_ROOT / "agents",
    ).run()
    run_json = json.loads((tmp_path / run_id / "run.json").read_text())
    assert run_json["is_quick_match"] is False
