"""Match runner — fast mode (in-process) and faithful mode (subprocess+HTTP).

Task 8 implements fast; Task 9 adds faithful.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


@dataclass
class MatchOutcome:
    agent_ids: list[str]
    winner: Optional[str]           # agent_id or None (draw / error)
    scores: list[int]               # final ship sum per player (planets + fleets)
    turns: int
    duration_s: float
    seed: int = 0                   # logged for audit; engine currently ignores it
    status: Literal["ok", "timeout", "crashed", "agent_failed_to_start", "invalid_action", "draw"] = "ok"
    # agent_failed_to_start is reserved for faithful mode (Task 9)
    replay: dict = field(default_factory=dict)


def _crashed_replay_skeleton(error: str) -> dict:
    """Produce a replay dict with the same top-level keys as env.toJSON()
    so downstream code (save_replay, viewer) doesn't KeyError on missing keys."""
    return {"error": error, "steps": [], "rewards": [], "statuses": []}


def run_match_fast(
    agent_ids: list[str],
    agent_paths: list[Path],
    *,
    seed: int = 0,
) -> MatchOutcome:
    """Run a single match in fast mode (kaggle-envs in-process).

    `agent_ids` order = player order (index 0 = player 0 = Q1 home).
    `agent_paths` must correspond 1:1 to agent_ids.

    `seed` is stored in the outcome for audit; kaggle-environments engine
    currently ignores the seed internally (per postmortem 2026-04-20).
    """
    if len(agent_ids) != len(agent_paths):
        raise ValueError(
            f"agent_ids and agent_paths length mismatch: "
            f"{len(agent_ids)} vs {len(agent_paths)}"
        )
    from kaggle_environments import make

    env = make("orbit_wars", debug=False)

    start = time.monotonic()
    try:
        env.run([str(p / "main.py") for p in agent_paths])
    except Exception as e:
        duration = time.monotonic() - start
        return MatchOutcome(
            agent_ids=agent_ids,
            winner=None,
            scores=[],
            turns=0,
            duration_s=duration,
            seed=seed,
            status="crashed",
            replay=_crashed_replay_skeleton(str(e)),
        )
    duration = time.monotonic() - start
    replay = env.toJSON()
    winner, scores, turns, status = _extract_outcome(replay, agent_ids)
    return MatchOutcome(
        agent_ids=agent_ids,
        winner=winner,
        scores=scores,
        turns=turns,
        duration_s=duration,
        seed=seed,
        status=status,  # type: ignore[arg-type]
        replay=replay,
    )


def _extract_outcome(
    replay: dict, agent_ids: list[str]
) -> tuple[Optional[str], list[int], int, str]:
    """Parse terminal state: winner, per-player scores, turn count, status."""
    steps = replay.get("steps") or []
    if not steps:
        return None, [], 0, "crashed"
    final_step = steps[-1]
    if not final_step:
        return None, [], 0, "crashed"

    num_players = len(agent_ids)
    rewards = [s.get("reward") for s in final_step]

    # Extract scores from last observation in state[0]
    state0 = final_step[0]
    obs = state0.get("observation", {})
    planets = obs.get("planets", [])
    fleets = obs.get("fleets", [])

    scores = [0] * num_players
    for p in planets:
        owner = p[1] if len(p) > 1 else -1
        ships = p[5] if len(p) > 5 else 0
        if 0 <= owner < num_players:
            scores[owner] += int(ships)
    for f in fleets:
        owner = f[1] if len(f) > 1 else -1
        ships = f[6] if len(f) > 6 else 0
        if 0 <= owner < num_players:
            scores[owner] += int(ships)

    # Winner: exactly one reward == 1
    winners_idx = [i for i, r in enumerate(rewards) if r == 1]
    if len(winners_idx) == 1:
        winner = agent_ids[winners_idx[0]]
    else:
        winner = None

    # Status based on any agent's final status
    statuses = [s.get("status") for s in final_step]
    if "ERROR" in statuses:
        status = "crashed"
    elif "TIMEOUT" in statuses:
        status = "timeout"
    elif "INVALID" in statuses:
        status = "invalid_action"
    elif winner is None:
        status = "draw"
    else:
        status = "ok"

    turns = len(steps)
    return winner, scores, turns, status


def run_match(
    agent_ids: list[str],
    agent_paths: list[Path],
    *,
    mode: Literal["fast", "faithful"] = "fast",
    seed: int = 0,
) -> MatchOutcome:
    """Dispatcher: fast (in-process) vs faithful (subprocess+HTTP)."""
    if mode == "fast":
        return run_match_fast(agent_ids, agent_paths, seed=seed)
    return run_match_faithful(agent_ids, agent_paths, seed=seed)


def run_match_faithful(
    agent_ids: list[str],
    agent_paths: list[Path],
    *,
    seed: int = 0,
) -> MatchOutcome:
    """Run match with each agent in its own subprocess + HTTP server.

    Uses kaggle-envs UrlAgent path — identical protocol to Kaggle production.
    """
    if len(agent_ids) != len(agent_paths):
        raise ValueError(
            f"agent_ids and agent_paths length mismatch: "
            f"{len(agent_ids)} vs {len(agent_paths)}"
        )
    from kaggle_environments import make

    from .agent_subprocess import spawn_agent, shutdown

    handles: list = []
    try:
        for aid, apath in zip(agent_ids, agent_paths):
            try:
                h = spawn_agent(apath, agent_id=aid)
                handles.append(h)
            except Exception as e:
                # One agent's spawn failed; report and abort this match
                return MatchOutcome(
                    agent_ids=agent_ids,
                    winner=None,
                    scores=[],
                    turns=0,
                    duration_s=0.0,
                    seed=seed,
                    status="agent_failed_to_start",
                    replay=_crashed_replay_skeleton(f"{aid}: {e}"),
                )

        urls = [h.url for h in handles]
        env = make("orbit_wars", debug=False)

        start = time.monotonic()
        try:
            env.run(urls)
        except Exception as e:
            duration = time.monotonic() - start
            return MatchOutcome(
                agent_ids=agent_ids,
                winner=None,
                scores=[],
                turns=0,
                duration_s=duration,
                seed=seed,
                status="crashed",
                replay=_crashed_replay_skeleton(str(e)),
            )
        duration = time.monotonic() - start
        replay = env.toJSON()
        winner, scores, turns, status = _extract_outcome(replay, agent_ids)
        return MatchOutcome(
            agent_ids=agent_ids,
            winner=winner,
            scores=scores,
            turns=turns,
            duration_s=duration,
            seed=seed,
            status=status,  # type: ignore[arg-type]
            replay=replay,
        )
    finally:
        for h in handles:
            shutdown(h)
