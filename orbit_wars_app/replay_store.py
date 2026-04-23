"""Save/load replay JSON (native env.toJSON() format from kaggle-environments)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def agent_id_to_safe(agent_id: str) -> str:
    """'mine/v1-combat-aware' → 'mine_v1-combat-aware' (no slashes in filenames)."""
    return agent_id.replace("/", "_")


def make_match_filename(match_id: int, agent_ids: list[str]) -> str:
    """Format: '<NNN>-<a>__vs__<b>[__vs__<c>__vs__<d>].json'."""
    safe = [agent_id_to_safe(a) for a in agent_ids]
    joined = "__vs__".join(safe)
    return f"{match_id:03d}-{joined}.json"


def save_replay(
    replays_dir: Path, match_id: int, agent_ids: list[str], replay: Any
) -> Path:
    """Write replay JSON. Overwrites if exists. Returns path."""
    replays_dir.mkdir(parents=True, exist_ok=True)
    path = replays_dir / make_match_filename(match_id, agent_ids)
    with path.open("w", encoding="utf-8") as f:
        json.dump(replay, f)
    return path


def load_replay(path: Path) -> Any:
    """Read replay JSON. Raises FileNotFoundError if missing."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
