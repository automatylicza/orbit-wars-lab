from __future__ import annotations

import argparse
import importlib
import math
import random
import sys
import types
from collections import namedtuple
from pathlib import Path
from typing import Any

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import TrainConfig, default_train_config_path, load_train_config
from src.features import TurnBatch, candidate_feature_dim, encode_turn, global_feature_dim, self_feature_dim
from src.policy import PlanetPolicy
from src.ppo import sample_actions

Planet = namedtuple("Planet", ["id", "owner", "x", "y", "radius", "ships", "production"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--config", type=str, default=str(default_train_config_path()))
    parser.add_argument("--checkpoint", type=str, default=None)
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--deterministic", action="store_true")
    return parser.parse_args()


def resolve_device(name: str) -> torch.device:
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_policy(cfg: TrainConfig, device: torch.device) -> PlanetPolicy:
    return PlanetPolicy(
        self_dim=self_feature_dim(),
        candidate_dim=candidate_feature_dim(),
        global_dim=global_feature_dim(),
        candidate_count=cfg.env.candidate_count,
        hidden_size=cfg.model.hidden_size,
    ).to(device)

def register_checkpoint_module_aliases() -> None:
    sys.modules.setdefault("src", types.ModuleType("src"))
    sys.modules.setdefault("src.rl_template", types.ModuleType("src.rl_template"))
    module_candidates = {
        "config": ["src.rl_template.config", "src.config", "config"],
        "features": ["src.rl_template.features", "src.features", "features"],
        "policy": ["src.rl_template.policy", "src.policy", "policy"],
        "ppo": ["src.rl_template.ppo", "src.ppo", "ppo"],
        "game_types": ["src.rl_template.game_types", "src.game_types", "game_types"],
        "opponents": ["src.rl_template.opponents", "src.opponents", "opponents"],
        "env": ["src.rl_template.env", "src.env", "env"],
        "train": ["src.rl_template.train", "src.train", "train"],
    }

    for canonical_name, candidates in module_candidates.items():
        module = None
        for candidate in candidates:
            try:
                module = importlib.import_module(candidate)
                break
            except ModuleNotFoundError:
                continue
        if module is None:
            continue
        sys.modules[f"src.rl_template.{canonical_name}"] = module
        sys.modules[f"src.{canonical_name}"] = module

def load_checkpoint_if_available(policy: PlanetPolicy, checkpoint_path: str | None, device: torch.device) -> None:
    register_checkpoint_module_aliases()
    if checkpoint_path is None:
        return
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    state_dict = checkpoint.get("policy", checkpoint)
    policy.load_state_dict(state_dict)


def build_moves(batch: TurnBatch, policy: PlanetPolicy, device: torch.device, deterministic: bool) -> list[list[float | int]]:
    if batch.self_features.shape[0] == 0:
        return []
    with torch.inference_mode():
        outputs = policy(
            torch.from_numpy(batch.self_features).to(device),
            torch.from_numpy(batch.candidate_features).to(device),
            torch.from_numpy(batch.global_features).to(device),
            torch.from_numpy(batch.candidate_mask).to(device).bool(),
        )
        sampled = sample_actions(outputs, deterministic=deterministic)
    target_indices = sampled.target_index.detach().cpu().numpy()

    moves: list[list[float | int]] = []
    for row_idx, context in enumerate(batch.contexts):
        target_idx = int(target_indices[row_idx])
        if target_idx == 0:
            continue
        if target_idx >= len(context.candidate_ids):
            continue
        if not context.candidate_mask[target_idx]:
            continue
        ships = int(context.ship_counts[target_idx])
        if ships <= 0:
            continue
        moves.append([context.source_id, float(context.target_angles[target_idx]), ships])
    return moves


def nearest_planet_sniper(obs: Any) -> list[list[float | int]]:
    moves: list[list[float | int]] = []
    player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    planets = [Planet(*p) for p in raw_planets]
    my_planets = [p for p in planets if p.owner == player]
    targets = [p for p in planets if p.owner != player]
    if not targets:
        return moves
    for mine in my_planets:
        nearest = None
        min_dist = float("inf")
        for target in targets:
            dist = math.hypot(mine.x - target.x, mine.y - target.y)
            if dist < min_dist:
                min_dist = dist
                nearest = target
        if nearest is None:
            continue
        ships_needed = max(nearest.ships + 1, 20)
        if mine.ships < ships_needed:
            continue
        angle = math.atan2(nearest.y - mine.y, nearest.x - mine.x)
        moves.append([mine.id, angle, ships_needed])
    return moves


def extract_observation(state: Any) -> Any:
    if isinstance(state, dict):
        return state.get("observation")
    return getattr(state, "observation")


def extract_status(state: Any) -> str:
    if isinstance(state, dict):
        return str(state.get("status", "UNKNOWN"))
    return str(getattr(state, "status", "UNKNOWN"))


def extract_reward(state: Any) -> float:
    if isinstance(state, dict):
        value = state.get("reward", 0.0)
    else:
        value = getattr(state, "reward", 0.0)
    return 0.0 if value is None else float(value)


def play_one_game(
    cfg: TrainConfig,
    policy: PlanetPolicy,
    device: torch.device,
    *,
    seed: int,
    deterministic: bool,
) -> tuple[float, int]:
    from kaggle_environments import make

    env = make(
        "orbit_wars",
        configuration={"seed": int(seed), "randomSeed": int(seed)},
        debug=False,
    )
    env.reset(num_agents=2)
    states = env.step([[], []])
    player_obs = extract_observation(states[0])
    opponent_obs = extract_observation(states[1])
    done = extract_status(states[0]) != "ACTIVE"
    step_count = 0

    while not done:
        batch = encode_turn(player_obs, cfg.env, env_index=0)
        player_action = build_moves(batch, policy, device, deterministic)
        opponent_action = nearest_planet_sniper(opponent_obs)
        states = env.step([player_action, opponent_action])
        player_obs = extract_observation(states[0])
        opponent_obs = extract_observation(states[1])
        done = extract_status(states[0]) != "ACTIVE"
        step_count += 1

    return extract_reward(states[0]), step_count


def reward_to_label(reward: float) -> str:
    if reward > 0:
        return "win"
    if reward < 0:
        return "loss"
    return "draw"


def main() -> None:
    args = parse_args()
    cfg = load_train_config(args.config)
    device_name = args.device if args.device != "auto" else cfg.device
    device = resolve_device(device_name)
    seed_everything(args.seed)
    policy = build_policy(cfg, device)
    load_checkpoint_if_available(policy, args.checkpoint, device)
    policy.eval()

    wins = 0
    draws = 0
    losses = 0

    for game_idx in range(args.games):
        game_seed = args.seed + game_idx
        reward, steps = play_one_game(
            cfg,
            policy,
            device,
            seed=game_seed,
            deterministic=args.deterministic,
        )
        label = reward_to_label(reward)
        if label == "win":
            wins += 1
        elif label == "loss":
            losses += 1
        else:
            draws += 1
        print(f"game={game_idx + 1} seed={game_seed} result={label} reward={reward:.1f} steps={steps}")

    total_games = max(args.games, 1)
    win_rate = wins / total_games
    print(f"summary wins={wins} losses={losses} draws={draws} games={args.games}")
    print(f"win_rate={win_rate:.4f}")


if __name__ == "__main__":
    main()
