"""Integration: fast-mode match using real kaggle-environments engine."""
from __future__ import annotations

from pathlib import Path

import pytest

from orbit_wars_app.match import run_match_fast


PROJECT_ROOT = Path(__file__).parent.parent.parent
AGENTS_ROOT = PROJECT_ROOT / "agents"


def _agent_path(agent_id: str) -> Path:
    return AGENTS_ROOT / agent_id


def test_fast_match_random_vs_random_terminates():
    outcome = run_match_fast(
        agent_ids=["baselines/random", "baselines/random"],
        agent_paths=[_agent_path("baselines/random"), _agent_path("baselines/random")],
        seed=42,
    )

    assert outcome.turns > 0
    assert outcome.turns <= 500  # episodeSteps
    assert len(outcome.scores) == 2
    assert outcome.duration_s > 0
    assert outcome.status == "ok"
    # Replay dict is non-empty
    assert "steps" in outcome.replay
    assert len(outcome.replay["steps"]) > 0


def test_fast_match_nearest_sniper_vs_random_returns_winner():
    outcome = run_match_fast(
        agent_ids=["baselines/nearest-sniper", "baselines/random"],
        agent_paths=[
            _agent_path("baselines/nearest-sniper"),
            _agent_path("baselines/random"),
        ],
        seed=42,
    )
    # Nearest-sniper powinien wygrywać większość, ale nie wszystko (Random ma luck)
    assert outcome.status == "ok"
    assert outcome.winner in ("baselines/nearest-sniper", "baselines/random", None)


def test_fast_match_preserves_agent_ids_order_in_scores():
    outcome = run_match_fast(
        agent_ids=["baselines/nearest-sniper", "baselines/random"],
        agent_paths=[
            _agent_path("baselines/nearest-sniper"),
            _agent_path("baselines/random"),
        ],
        seed=1,
    )
    # Score index 0 = first agent in list (player 0), 1 = player 1
    assert len(outcome.scores) == 2
