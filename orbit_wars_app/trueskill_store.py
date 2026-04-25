"""Persistent TrueSkill ratings per agent_id per format ('2p' / '4p')."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import trueskill

from .schemas import Format, Rating


TS_MU_0 = 600.0
TS_SIGMA_0 = 200.0
TS_BETA = 100.0
TS_TAU = 2.0
TS_DRAW_PROB = 0.05

_env = trueskill.TrueSkill(
    mu=TS_MU_0,
    sigma=TS_SIGMA_0,
    beta=TS_BETA,
    tau=TS_TAU,
    draw_probability=TS_DRAW_PROB,
)


class TrueSkillStore:
    """Load/save persistent ratings JSON. Update per match."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Path):
        self.path = path
        self._ratings: dict[str, dict[str, dict]] = {}  # agent_id → format → {mu, sigma, games_played}
        self._load()

    def _load(self):
        if not self.path.is_file():
            return
        data = json.loads(self.path.read_text())
        if data.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version {data.get('schema_version')}; expected {self.SCHEMA_VERSION}"
            )
        self._ratings = data.get("ratings", {})

    def get_rating(self, agent_id: str, *, format: Format) -> Rating:
        per_format = self._ratings.get(agent_id, {}).get(format)
        if per_format is None:
            mu, sigma, games = TS_MU_0, TS_SIGMA_0, 0
        else:
            mu = per_format["mu"]
            sigma = per_format["sigma"]
            games = per_format["games_played"]
        return Rating(
            agent_id=agent_id,
            mu=mu,
            sigma=sigma,
            conservative=mu - 3 * sigma,
            games_played=games,
        )

    def update_match(
        self,
        *,
        agent_ids: list[str],
        winner: Optional[str],
        format: Format,
        scores: Optional[list[float]] = None,
    ) -> None:
        """Apply TrueSkill update for one match.

        winner: agent_id of sole winner, or None for draw.
        scores: per-agent final scores aligned to agent_ids. When provided,
            ranks are derived from the full score ordering (dense rank, higher
            score = better) — essential for 4p FFA so 2nd/3rd/4th don't all
            collapse into a single loser tier. When omitted, falls back to
            the winner-vs-rest heuristic (fine for 2p).
        """
        # Build current ratings
        ratings = [self._as_trueskill_rating(aid, format) for aid in agent_ids]

        # Rank convention: TrueSkill ranks lower = better.
        if scores is not None and len(scores) == len(agent_ids):
            # Dense rank: highest score → 0, next distinct score → 1, etc.
            # Equal scores share a rank. Preserves full ordering for 4p FFA.
            unique_desc = sorted({s for s in scores}, reverse=True)
            score_to_rank = {s: i for i, s in enumerate(unique_desc)}
            ranks = [score_to_rank[s] for s in scores]
        elif winner is None:
            # No scores, no winner → pure draw.
            ranks = [0] * len(agent_ids)
        else:
            ranks = [0 if aid == winner else 1 for aid in agent_ids]

        # TrueSkill.rate expects list of teams (each team = list of ratings)
        rating_teams = [[r] for r in ratings]
        new_teams = _env.rate(rating_teams, ranks=ranks)

        # Flatten back
        for aid, team in zip(agent_ids, new_teams):
            new_rating = team[0]
            per_fmt = self._ratings.setdefault(aid, {}).setdefault(
                format, {"mu": TS_MU_0, "sigma": TS_SIGMA_0, "games_played": 0}
            )
            per_fmt["mu"] = float(new_rating.mu)
            per_fmt["sigma"] = float(new_rating.sigma)
            per_fmt["games_played"] = per_fmt["games_played"] + 1

    def _as_trueskill_rating(self, agent_id: str, format: Format) -> trueskill.Rating:
        per_fmt = self._ratings.get(agent_id, {}).get(format)
        if per_fmt is None:
            return _env.create_rating()
        return _env.create_rating(mu=per_fmt["mu"], sigma=per_fmt["sigma"])

    def leaderboard(self, *, format: Format) -> list[Rating]:
        """Return sorted ratings (conservative desc)."""
        out: list[Rating] = []
        for aid, per_fmt in self._ratings.items():
            if format not in per_fmt:
                continue
            pf = per_fmt[format]
            out.append(
                Rating(
                    agent_id=aid,
                    mu=pf["mu"],
                    sigma=pf["sigma"],
                    conservative=pf["mu"] - 3 * pf["sigma"],
                    games_played=pf["games_played"],
                )
            )
        out.sort(key=lambda r: r.conservative, reverse=True)
        for i, r in enumerate(out, start=1):
            r.rank = i
        return out

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": self.SCHEMA_VERSION,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "ratings": self._ratings,
        }
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.replace(self.path)

    def snapshot_to(self, dest: Path) -> None:
        """Copy current file to dest (for runs/<ts>/trueskill.json snapshots)."""
        if not self.path.is_file():
            self.save()
        shutil.copy2(self.path, dest)
