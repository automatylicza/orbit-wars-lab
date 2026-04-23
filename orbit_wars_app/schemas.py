"""Pydantic models for Orbit Wars Lab."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


Bucket = Literal["baselines", "external", "mine"]
Format = Literal["2p", "4p"]
Mode = Literal["fast", "faithful"]
TournamentShape = Literal["round-robin", "gauntlet"]
MatchStatus = Literal[
    "ok", "timeout", "crashed", "agent_failed_to_start", "invalid_action", "draw"
]
RunStatus = Literal["running", "completed", "aborted"]


class AgentInfo(BaseModel):
    """Metadata for one agent, as scanned from `agents/**/`."""

    id: str = Field(..., description="Relative path: 'baselines/random'")
    name: str
    bucket: Bucket
    description: Optional[str] = None
    author: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    disabled: bool = False
    has_yaml: bool
    path: str = Field(..., description="Relative path from project root: 'agents/baselines/random'")
    last_error: Optional[str] = None

    # ===== External agent fields (None for baselines/mine) =====
    kernel_slug: Optional[str] = Field(
        default=None,
        description="Kaggle notebook identifier: '<owner>/<slug>' — key for re-fetching",
    )
    kernel_version: Optional[int] = Field(
        default=None,
        description="Numer wersji notebooka na Kaggle w momencie pobrania",
    )
    date_fetched: Optional[str] = None
    license: Optional[str] = None
    author_claimed_lb_score: Optional[float] = Field(
        default=None,
        description="LB score extracted from notebook title — hint, NIE nasza prawda",
    )

    # ===== DEPRECATED fields (zachowane dla backward compat, discovery.py loguje warning) =====
    source_url: Optional[str] = Field(
        default=None,
        description="DEPRECATED — generujemy z kernel_slug. Backward compat only.",
    )
    version: Optional[str] = Field(
        default=None,
        description="DEPRECATED — zastąpione przez kernel_version (typed int).",
    )


class Rating(BaseModel):
    agent_id: str
    mu: float
    sigma: float
    conservative: float
    games_played: int
    rank: int = 0


class MatchResult(BaseModel):
    match_id: str
    agent_ids: list[str]
    winner: Optional[str] = None
    scores: list[int] = Field(default_factory=list)
    turns: int = 0
    duration_s: float = 0.0
    status: MatchStatus = "ok"
    seed: int = 0
    replay_path: str = ""


class RunSummary(BaseModel):
    id: str
    started_at: str
    finished_at: Optional[str] = None
    mode: Mode = "fast"
    format: Format = "2p"
    status: RunStatus = "running"
    total_matches: int = 0
    matches_done: int = 0
    is_quick_match: bool = False  # Propagowane z TournamentConfig, serializowane do run.json


class TournamentConfig(BaseModel):
    agents: list[str]
    games_per_pair: int = 3
    mode: Mode = "fast"
    format: Format = "2p"
    parallel: int = 1
    seed_base: int = 42
    is_quick_match: bool = False  # True gdy uruchomione z Quick Match UI (filtrowane z /api/runs?exclude_quick_match=true)
    shape: TournamentShape = "round-robin"
    # Required when shape="gauntlet". Must be present in agents. The runner
    # pairs the challenger against each remaining agent × games_per_pair.
    challenger_id: Optional[str] = None
