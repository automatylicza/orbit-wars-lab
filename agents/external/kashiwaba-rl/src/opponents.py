from __future__ import annotations

from typing import Any, Protocol

import torch

from .config import TrainConfig
from .features import encode_turn
from .policy import PlanetPolicy
from .ppo import sample_actions


class OpponentPolicy(Protocol):
    def act(self, observation: Any) -> list[list[float | int]]:
        ...


class KaggleRandomOpponent:
    def __init__(self) -> None:
        from kaggle_environments.envs.orbit_wars.orbit_wars import random_agent

        self._agent = random_agent

    def act(self, observation: Any) -> list[list[float | int]]:
        payload = {
            "player": obs_get(observation, "player", 0),
            "planets": list(obs_get(observation, "planets", [])),
        }
        return list(self._agent(payload))


class SelfPlayOpponent:
    def __init__(self, cfg: TrainConfig, device: torch.device, deterministic: bool = True) -> None:
        from .features import candidate_feature_dim, global_feature_dim, self_feature_dim

        self.cfg = cfg
        self.device = device
        self.deterministic = deterministic
        self.policy = PlanetPolicy(
            self_dim=self_feature_dim(),
            candidate_dim=candidate_feature_dim(),
            global_dim=global_feature_dim(),
            candidate_count=cfg.env.candidate_count,
            hidden_size=cfg.model.hidden_size,
        ).to(device)
        self.policy.eval()

    def sync_from(self, source_policy: PlanetPolicy) -> None:
        self.policy.load_state_dict(source_policy.state_dict())
        self.policy.eval()

    def act(self, observation: Any) -> list[list[float | int]]:
        batch = encode_turn(observation, self.cfg.env, env_index=0)
        if batch.self_features.shape[0] == 0:
            return []
        with torch.inference_mode():
            outputs = self.policy(
                torch.from_numpy(batch.self_features).to(self.device),
                torch.from_numpy(batch.candidate_features).to(self.device),
                torch.from_numpy(batch.global_features).to(self.device),
                torch.from_numpy(batch.candidate_mask).to(self.device).bool(),
            )
            sampled = sample_actions(outputs, deterministic=self.deterministic)
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


def build_opponent(
    name: str,
    cfg: TrainConfig | None = None,
    device: torch.device | None = None,
) -> OpponentPolicy:
    if name == "random":
        return KaggleRandomOpponent()
    if name == "self":
        if cfg is None or device is None:
            raise ValueError("cfg and device are required for self opponent")
        return SelfPlayOpponent(cfg, device=device, deterministic=cfg.self_play_deterministic)
    raise ValueError(f"Unknown opponent: {name}")


def obs_get(observation: Any, key: str, default: Any) -> Any:
    if isinstance(observation, dict):
        return observation.get(key, default)
    return getattr(observation, key, default)
