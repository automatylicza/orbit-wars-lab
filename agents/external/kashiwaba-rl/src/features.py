from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import EnvConfig
from .game_types import GameState, PlanetState, parse_observation

BOARD_CENTER = (50.0, 50.0)
ROTATION_RADIUS_LIMIT = 50.0
SUN_RADIUS = 10.0
PLANET_LAUNCH_RADIUS_OFFSET = 0.1


@dataclass(slots=True)
class DecisionContext:
    env_index: int
    source_id: int
    candidate_ids: list[int]
    candidate_mask: np.ndarray
    ship_counts: list[int]
    target_angles: list[float]


@dataclass(slots=True)
class TurnBatch:
    self_features: np.ndarray
    candidate_features: np.ndarray
    global_features: np.ndarray
    candidate_mask: np.ndarray
    contexts: list[DecisionContext]
    state: GameState


def self_feature_dim() -> int:
    return 11


def candidate_feature_dim() -> int:
    return 14


def global_feature_dim() -> int:
    return 8


def encode_turn(
    observation: Any,
    env_cfg: EnvConfig,
    *,
    env_index: int = 0,
) -> TurnBatch:
    state = observation if isinstance(observation, GameState) else parse_observation(observation)
    my_planets = sorted((planet for planet in state.planets if planet.owner == state.player), key=lambda planet: planet.id)
    if not my_planets:
        return TurnBatch(
            self_features=np.zeros((0, self_feature_dim()), dtype=np.float32),
            candidate_features=np.zeros((0, env_cfg.candidate_count, candidate_feature_dim()), dtype=np.float32),
            global_features=np.zeros((0, global_feature_dim()), dtype=np.float32),
            candidate_mask=np.zeros((0, env_cfg.candidate_count), dtype=bool),
            contexts=[],
            state=state,
        )

    global_feat = build_global_features(state, env_cfg)
    self_rows: list[np.ndarray] = []
    candidate_rows: list[np.ndarray] = []
    candidate_masks: list[np.ndarray] = []
    contexts: list[DecisionContext] = []

    for src in my_planets:
        candidates = build_candidates(src, state, env_cfg)
        cand_feat, cand_mask, ship_counts, candidate_ids, target_angles = build_candidate_features(
            src,
            candidates,
            state,
            env_cfg,
        )
        self_rows.append(build_self_features(src, state, env_cfg))
        candidate_rows.append(cand_feat)
        candidate_masks.append(cand_mask)
        contexts.append(
            DecisionContext(
                env_index=env_index,
                source_id=src.id,
                candidate_ids=candidate_ids,
                candidate_mask=cand_mask,
                ship_counts=ship_counts,
                target_angles=target_angles,
            )
        )

    return TurnBatch(
        self_features=np.asarray(self_rows, dtype=np.float32),
        candidate_features=np.asarray(candidate_rows, dtype=np.float32),
        global_features=np.repeat(global_feat[None, :], len(self_rows), axis=0),
        candidate_mask=np.asarray(candidate_masks, dtype=bool),
        contexts=contexts,
        state=state,
    )


def build_candidates(src: PlanetState, state: GameState, env_cfg: EnvConfig) -> list[PlanetState]:
    others = [planet for planet in state.planets if planet.id != src.id]
    enemy_quota = env_cfg.candidate_count // 3
    neutral_quota = env_cfg.candidate_count // 3
    friendly_quota = env_cfg.candidate_count - enemy_quota - neutral_quota

    enemies = sorted(
        (planet for planet in others if planet.owner not in {-1, state.player}),
        key=lambda planet: (distance(src, planet), planet.id),
    )[:enemy_quota]
    neutrals = sorted(
        (planet for planet in others if planet.owner == -1),
        key=lambda planet: (distance(src, planet), planet.id),
    )[:neutral_quota]
    friendlies = sorted(
        (planet for planet in others if planet.owner == state.player),
        key=lambda planet: (distance(src, planet), planet.id),
    )[:friendly_quota]

    selected_ids = {planet.id for planet in enemies + neutrals + friendlies}
    candidates = enemies + neutrals + friendlies
    if len(candidates) >= env_cfg.candidate_count:
        return candidates[: env_cfg.candidate_count]

    fallback = sorted(
        (planet for planet in others if planet.id not in selected_ids),
        key=lambda planet: (distance(src, planet), planet.id),
    )
    candidates.extend(fallback[: env_cfg.candidate_count - len(candidates)])
    return candidates


def build_self_features(src: PlanetState, state: GameState, env_cfg: EnvConfig) -> np.ndarray:
    my_planets = [planet for planet in state.planets if planet.owner == state.player]
    enemy_planets = [planet for planet in state.planets if planet.owner not in {-1, state.player}]
    return np.asarray(
        [
            1.0,
            src.x / env_cfg.board_size,
            src.y / env_cfg.board_size,
            src.radius / 5.0,
            min(src.ships, env_cfg.max_ships) / env_cfg.max_ships,
            src.production / env_cfg.max_production,
            1.0 if is_rotating_planet(src) else 0.0,
            len(my_planets) / env_cfg.max_planets,
            len(enemy_planets) / env_cfg.max_planets,
            total_ships(my_planets) / (env_cfg.max_planets * env_cfg.max_ships),
            total_ships(enemy_planets) / (env_cfg.max_planets * env_cfg.max_ships),
        ],
        dtype=np.float32,
    )


def build_candidate_features(
    src: PlanetState,
    candidates: list[PlanetState],
    state: GameState,
    env_cfg: EnvConfig,
) -> tuple[np.ndarray, np.ndarray, list[int], list[int], list[float]]:
    features = np.zeros((env_cfg.candidate_count, candidate_feature_dim()), dtype=np.float32)
    candidate_mask = np.zeros((env_cfg.candidate_count,), dtype=bool)
    ship_counts = [0] * env_cfg.candidate_count
    candidate_ids = [-1] * env_cfg.candidate_count
    target_angles = [0.0] * env_cfg.candidate_count
    candidate_mask[0] = True

    for idx, tgt in enumerate(candidates, start=1):
        if idx >= env_cfg.candidate_count:
            break
        dx = tgt.x - src.x
        dy = tgt.y - src.y
        angle = math.atan2(dy, dx)
        crosses_sun = shot_crosses_sun(src, angle, tgt)
        ships_needed = fixed_ship_count(src, tgt)
        features[idx] = np.asarray(
            [
                1.0,
                1.0 if tgt.owner == -1 else 0.0,
                1.0 if tgt.owner == state.player else 0.0,
                1.0 if tgt.owner not in {-1, state.player} else 0.0,
                tgt.x / env_cfg.board_size,
                tgt.y / env_cfg.board_size,
                dx / env_cfg.board_size,
                dy / env_cfg.board_size,
                distance(src, tgt) / env_cfg.board_size,
                min(tgt.ships, env_cfg.max_ships) / env_cfg.max_ships,
                tgt.production / env_cfg.max_production,
                1.0 if is_rotating_planet(tgt) else 0.0,
                1.0 if crosses_sun else 0.0,
                min(src.ships, env_cfg.max_ships) / env_cfg.max_ships,
            ],
            dtype=np.float32,
        )
        ship_counts[idx] = ships_needed
        candidate_mask[idx] = ships_needed > 0 and not crosses_sun and src.ships >= ships_needed
        candidate_ids[idx] = tgt.id
        target_angles[idx] = angle

    return features, candidate_mask, ship_counts, candidate_ids, target_angles


def build_global_features(state: GameState, env_cfg: EnvConfig) -> np.ndarray:
    my_planets = [planet for planet in state.planets if planet.owner == state.player]
    enemy_planets = [planet for planet in state.planets if planet.owner not in {-1, state.player}]
    neutral_planets = [planet for planet in state.planets if planet.owner == -1]
    my_fleets = [fleet for fleet in state.fleets if fleet.owner == state.player]
    enemy_fleets = [fleet for fleet in state.fleets if fleet.owner != state.player]
    return np.asarray(
        [
            state.step / env_cfg.episode_steps,
            len(my_planets) / env_cfg.max_planets,
            len(enemy_planets) / env_cfg.max_planets,
            len(neutral_planets) / env_cfg.max_planets,
            total_ships(my_planets) / (env_cfg.max_planets * env_cfg.max_ships),
            total_ships(enemy_planets) / (env_cfg.max_planets * env_cfg.max_ships),
            sum(fleet.ships for fleet in my_fleets) / (env_cfg.max_planets * env_cfg.max_ships),
            sum(fleet.ships for fleet in enemy_fleets) / (env_cfg.max_planets * env_cfg.max_ships),
        ],
        dtype=np.float32,
    )


def fixed_ship_count(src: PlanetState, tgt: PlanetState) -> int:
    return max(tgt.ships + 1, 20)


def distance(a: PlanetState, b: PlanetState) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def total_ships(planets: list[PlanetState]) -> float:
    return float(sum(planet.ships for planet in planets))


def is_rotating_planet(planet: PlanetState) -> bool:
    dx = planet.x - BOARD_CENTER[0]
    dy = planet.y - BOARD_CENTER[1]
    orbital_radius = math.hypot(dx, dy)
    return orbital_radius + planet.radius < ROTATION_RADIUS_LIMIT


def shot_crosses_sun(src: PlanetState, angle: float, tgt: PlanetState) -> bool:
    start_x = src.x + math.cos(angle) * (src.radius + PLANET_LAUNCH_RADIUS_OFFSET)
    start_y = src.y + math.sin(angle) * (src.radius + PLANET_LAUNCH_RADIUS_OFFSET)
    return point_to_segment_distance(BOARD_CENTER, (start_x, start_y), (tgt.x, tgt.y)) < SUN_RADIUS


def point_to_segment_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    segment_len_sq = (start[0] - end[0]) ** 2 + (start[1] - end[1]) ** 2
    if segment_len_sq == 0.0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    projection = (
        ((point[0] - start[0]) * (end[0] - start[0]) + (point[1] - start[1]) * (end[1] - start[1]))
        / segment_len_sq
    )
    projection = max(0.0, min(1.0, projection))
    closest_x = start[0] + projection * (end[0] - start[0])
    closest_y = start[1] + projection * (end[1] - start[1])
    return math.hypot(point[0] - closest_x, point[1] - closest_y)
