"""kashiwaba RL PPO agent — 2000-update checkpoint.

Per tutorial's win-rate table, this checkpoint beats nearest-planet-sniper
100% of the time (20/20 games, deterministic). Loads policy at module init,
then runs inference per turn.

Source: notebook cells 9 + 11-15 + 37 (play_vs_sniper.py structure).
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import torch

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from src.config import load_train_config  # noqa: E402
from src.features import (  # noqa: E402
    candidate_feature_dim,
    encode_turn,
    global_feature_dim,
    self_feature_dim,
)
from src.policy import PlanetPolicy  # noqa: E402
from src.ppo import sample_actions  # noqa: E402


def _register_module_aliases() -> None:
    """Checkpoint was pickled against src.rl_template.* paths in some cases —
    map those to our src.* modules so torch.load can resolve classes."""
    sys.modules.setdefault("src.rl_template", types.ModuleType("src.rl_template"))
    for name in ("config", "features", "policy", "ppo", "game_types", "opponents", "env", "train"):
        try:
            mod = importlib.import_module(f"src.{name}")
        except ModuleNotFoundError:
            continue
        sys.modules[f"src.rl_template.{name}"] = mod


def _load_policy() -> tuple:
    cfg = load_train_config(str(_HERE / "default_cfg.yaml"))
    device = torch.device("cpu")
    policy = PlanetPolicy(
        self_dim=self_feature_dim(),
        candidate_dim=candidate_feature_dim(),
        global_dim=global_feature_dim(),
        candidate_count=cfg.env.candidate_count,
        hidden_size=cfg.model.hidden_size,
    ).to(device)
    _register_module_aliases()
    ckpt_path = _HERE / "weights" / "ckpt_002000.pt"
    ckpt = torch.load(str(ckpt_path), map_location=device, weights_only=False)
    state_dict = ckpt.get("policy", ckpt) if isinstance(ckpt, dict) else ckpt
    policy.load_state_dict(state_dict)
    policy.eval()
    return cfg, policy, device


_CFG, _POLICY, _DEVICE = _load_policy()


def agent(obs):
    batch = encode_turn(obs, _CFG.env, env_index=0)
    if batch.self_features.shape[0] == 0:
        return []
    with torch.inference_mode():
        outputs = _POLICY(
            torch.from_numpy(batch.self_features).to(_DEVICE),
            torch.from_numpy(batch.candidate_features).to(_DEVICE),
            torch.from_numpy(batch.global_features).to(_DEVICE),
            torch.from_numpy(batch.candidate_mask).to(_DEVICE).bool(),
        )
        sampled = sample_actions(outputs, deterministic=True)
    target_indices = sampled.target_index.detach().cpu().numpy()
    moves: list[list[float | int]] = []
    for row_idx, context in enumerate(batch.contexts):
        target_idx = int(target_indices[row_idx])
        if target_idx == 0 or target_idx >= len(context.candidate_ids):
            continue
        if not context.candidate_mask[target_idx]:
            continue
        ships = int(context.ship_counts[target_idx])
        if ships <= 0:
            continue
        moves.append([context.source_id, float(context.target_angles[target_idx]), ships])
    return moves
