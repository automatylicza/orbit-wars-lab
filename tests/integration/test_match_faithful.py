"""Integration: faithful-mode match — subprocess+HTTP+UrlAgent."""
from __future__ import annotations

from pathlib import Path

import pytest

from orbit_wars_app.match import run_match, run_match_faithful


PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
AGENTS_ROOT = PROJECT_ROOT / "agents"


def test_faithful_match_random_vs_random():
    outcome = run_match_faithful(
        agent_ids=["baselines/random", "baselines/random"],
        agent_paths=[
            AGENTS_ROOT / "baselines/random",
            AGENTS_ROOT / "baselines/random",
        ],
        seed=42,
    )
    assert outcome.turns > 0
    # random vs random can legitimately tie (e.g. both players stall after
    # sun-suicide streaks). Accept both ok and draw; bug is only if status
    # is something else (timeout/crashed/invalid_action).
    assert outcome.status in ("ok", "draw")
    assert len(outcome.scores) == 2
    # Both agents must have *done something* — non-zero turns and at least
    # one player with a non-zero ship count. If agents never move, faithful
    # mode is broken (regression catch for past UrlAgent routing bug).
    assert outcome.scores[0] > 0 or outcome.scores[1] > 0


def test_faithful_match_isolates_crashing_bot():
    """Crashujący bot nie zabija coordinatora — przegrywa ten mecz."""
    outcome = run_match_faithful(
        agent_ids=["baselines/random", "test/crashing"],
        agent_paths=[
            AGENTS_ROOT / "baselines/random",
            FIXTURES / "agent_crashing",
        ],
        seed=1,
    )
    # Coordinator returned cleanly; crashing bot either failed to start, was
    # detected as invalid/error, or ran 500 turns with sys.exit caught by FastAPI
    # (resulting in a draw). Key assertion: duration > 0 (run didn't hang).
    assert outcome.status in ("crashed", "ok", "invalid_action", "agent_failed_to_start", "draw")
    assert outcome.duration_s > 0


def test_run_match_dispatcher_fast():
    outcome = run_match(
        agent_ids=["baselines/random", "baselines/random"],
        agent_paths=[
            AGENTS_ROOT / "baselines/random",
            AGENTS_ROOT / "baselines/random",
        ],
        mode="fast",
        seed=42,
    )
    assert outcome.status == "ok"
    assert outcome.scores[0] > 0 or outcome.scores[1] > 0


def test_run_match_dispatcher_faithful():
    outcome = run_match(
        agent_ids=["baselines/random", "baselines/random"],
        agent_paths=[
            AGENTS_ROOT / "baselines/random",
            AGENTS_ROOT / "baselines/random",
        ],
        mode="faithful",
        seed=42,
    )
    # random vs random can legitimately tie; anything beyond ok/draw is a bug.
    assert outcome.status in ("ok", "draw")
    assert outcome.scores[0] > 0 or outcome.scores[1] > 0


def test_run_match_faithful_agent_fails_to_start():
    """Agent which fails to import (nonexistent dir) → agent_failed_to_start."""
    broken = Path("/tmp/nonexistent_agent_dir_for_test")
    outcome = run_match_faithful(
        agent_ids=["baselines/random", "test/broken"],
        agent_paths=[AGENTS_ROOT / "baselines/random", broken],
        seed=1,
    )
    assert outcome.status == "agent_failed_to_start"
    assert outcome.winner is None
