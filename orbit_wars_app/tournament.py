"""Tournament runner — round-robin pairs, K games each, persistent TrueSkill."""
from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .discovery import scan_zoo
from .match import run_match
from .replay_store import save_replay
from .schemas import AgentInfo, MatchResult, RunStatus, TournamentConfig
from .trueskill_store import TrueSkillStore


def _filter_agents_by_tags(
    agents: list["AgentInfo"],
    include: list[str],
    exclude: list[str],
) -> list["AgentInfo"]:
    """Filter agents by tags.

    Semantics:
    - `include=[]` → all (then exclude can still trim)
    - `include=[a, b, ...]` → any tag from the list must be present (OR)
    - `exclude=[a, b, ...]` → none of these tags may be present (AND)
    - `disabled: true` → always skipped

    Returns the list in original order.
    """
    out = []
    inc_set = set(include)
    exc_set = set(exclude)
    for a in agents:
        if a.disabled:
            continue
        tag_set = set(a.tags)
        if inc_set and not (tag_set & inc_set):
            continue
        if exc_set and (tag_set & exc_set):
            continue
        out.append(a)
    return out


class Tournament:
    """Round-robin: C(n,2) pairs × K games. Persist results.json, config.json,
    trueskill.json snapshot + update global runs/trueskill.json."""

    def __init__(
        self,
        config: TournamentConfig,
        *,
        runs_root: Path,
        zoo_root: Path,
    ):
        self.config = config
        self.runs_root = runs_root
        self.zoo_root = zoo_root

    def run(
        self,
        on_match_done: Optional[Callable[["MatchResult", int, int], None]] = None,
    ) -> str:
        """Execute tournament. Return run_id (directory name).

        `on_match_done(match_result, done_count, total_count)` is called after
        each match completes, for progress streaming (used by Plan B backend).
        """
        # Validate config BEFORE creating run_dir — so that an invalid
        # agent_id doesn't leave an orphan empty directory (which would
        # also bump the -NNN counter, creating numbering gaps).
        agents = self._resolve_agents()
        pairs = self._generate_pairs(agents)
        total_matches = len(pairs) * self.config.games_per_pair

        run_id = self._new_run_id()
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True)
        replays_dir = run_dir / "replays"
        replays_dir.mkdir()

        started_at = datetime.now(timezone.utc).isoformat()
        self._write_run_json(
            run_dir, run_id, started_at, None, "running", total_matches, 0
        )

        persistent_path = self.runs_root / "trueskill.json"
        store = TrueSkillStore(persistent_path)

        matches: list[MatchResult] = []
        rng = random.Random(self.config.seed_base)

        status: RunStatus = "completed"
        match_counter = 0
        try:
            for pair in pairs:
                for _ in range(self.config.games_per_pair):
                    match_counter += 1
                    seed = rng.randrange(10**9)
                    aids = [a["id"] for a in pair]
                    apaths = [self.zoo_root.parent / a["path"] for a in pair]

                    outcome = run_match(
                        agent_ids=aids,
                        agent_paths=apaths,
                        mode=self.config.mode,
                        seed=seed,
                    )

                    replay_rel = ""
                    if outcome.replay and "steps" in outcome.replay:
                        rp = save_replay(
                            replays_dir, match_counter, aids, outcome.replay
                        )
                        replay_rel = str(rp.relative_to(run_dir))

                    if outcome.status != "agent_failed_to_start":
                        store.update_match(
                            agent_ids=aids,
                            winner=outcome.winner,
                            format=self.config.format,
                        )

                    match_result = MatchResult(
                        match_id=f"{match_counter:03d}",
                        agent_ids=aids,
                        winner=outcome.winner,
                        scores=outcome.scores,
                        turns=outcome.turns,
                        duration_s=outcome.duration_s,
                        status=outcome.status,  # type: ignore[arg-type]
                        seed=seed,
                        replay_path=replay_rel,
                    )
                    matches.append(match_result)

                    # Streaming callback — any exception in callback is
                    # user's problem, not ours; let it propagate.
                    if on_match_done is not None:
                        on_match_done(match_result, match_counter, total_matches)
        except BaseException:
            status = "aborted"
            raise
        finally:
            # Persist partial state no matter what
            store.save()
            store.snapshot_to(run_dir / "trueskill.json")

            finished_at = datetime.now(timezone.utc).isoformat()
            self._write_run_json(
                run_dir, run_id, started_at, finished_at, status,
                total_matches, match_counter,
            )

            # config + results always written (partial on abort)
            (run_dir / "config.json").write_text(json.dumps({
                "mode": self.config.mode,
                "format": self.config.format,
                "games_per_pair": self.config.games_per_pair,
                "agents": self.config.agents,
                "seed_base": self.config.seed_base,
                "parallel": self.config.parallel,
                "started_at": started_at,
            }, indent=2))

            summary = self._build_summary(matches)
            (run_dir / "results.json").write_text(json.dumps({
                "started_at": started_at,
                "finished_at": finished_at,
                "total_matches": total_matches,
                "matches": [m.model_dump() for m in matches],
                "summary": summary,
                "status": status,
            }, indent=2))

            # 'latest' symlink (best-effort)
            latest = self.runs_root / "latest"
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            try:
                latest.symlink_to(run_id, target_is_directory=True)
            except (OSError, NotImplementedError):
                (self.runs_root / "latest.txt").write_text(run_id)

        return run_id

    def _write_run_json(
        self,
        run_dir: Path,
        run_id: str,
        started_at: str,
        finished_at: Optional[str],
        status: RunStatus,
        total_matches: int,
        matches_done: int,
    ) -> None:
        """Write run.json lifecycle file.

        run.json is the UI's single source for run lifecycle state; it
        intentionally duplicates mode/format from config.json so the
        web UI doesn't need to read two files per run.
        """
        payload = {
            "id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "mode": self.config.mode,
            "format": self.config.format,
            "status": status,
            "total_matches": total_matches,
            "matches_done": matches_done,
            "is_quick_match": self.config.is_quick_match,
        }
        (run_dir / "run.json").write_text(json.dumps(payload, indent=2))

    def _new_run_id(self) -> str:
        """YYYY-MM-DD-NNN — N increments for runs created the same day."""
        now = datetime.now(timezone.utc)
        prefix = now.strftime("%Y-%m-%d")
        existing = [
            p for p in self.runs_root.iterdir()
            if p.is_dir() and p.name.startswith(prefix)
        ]
        n = len(existing) + 1
        return f"{prefix}-{n:03d}"

    def _resolve_agents(self) -> list[dict]:
        """Look up AgentInfo for each requested agent_id.

        Returns list of dicts with `id` and `path` fields.
        """
        all_agents = {a.id: a for a in scan_zoo(self.zoo_root)}
        out: list[dict] = []
        for aid in self.config.agents:
            info = all_agents.get(aid)
            if info is None:
                raise ValueError(
                    f"Agent {aid!r} not found in zoo {self.zoo_root}. "
                    f"Available: {sorted(all_agents)}"
                )
            if info.disabled:
                raise ValueError(
                    f"Agent {aid!r} is disabled; remove from config or un-disable"
                )
            out.append({"id": info.id, "path": info.path})
        return out

    def _generate_pairs(self, agents: list[dict]) -> list[tuple[dict, ...]]:
        """round-robin: C(n,2) pairs (2p) or C(n,4) 4-tuples (4p).
        gauntlet: challenger × each opponent (2p), or challenger + C(n-1,3) (4p)."""
        if self.config.shape == "gauntlet":
            return self._generate_gauntlet_pairs(agents)
        if self.config.format == "2p":
            return list(itertools.combinations(agents, 2))
        # 4p round-robin
        if len(agents) < 4:
            raise ValueError(f"4p format needs ≥4 agents, got {len(agents)}")
        return list(itertools.combinations(agents, 4))

    def _generate_gauntlet_pairs(self, agents: list[dict]) -> list[tuple[dict, ...]]:
        cid = self.config.challenger_id
        if cid is None:
            raise ValueError("gauntlet requires challenger_id")
        challenger = next((a for a in agents if a["id"] == cid), None)
        if challenger is None:
            raise ValueError(f"challenger {cid!r} not in selected agents")
        opponents = [a for a in agents if a["id"] != cid]
        if self.config.format == "2p":
            if not opponents:
                raise ValueError("gauntlet needs ≥1 opponent")
            return [(challenger, opp) for opp in opponents]
        # 4p gauntlet: challenger + every 3-tuple of opponents
        if len(opponents) < 3:
            raise ValueError(f"4p gauntlet needs ≥3 opponents, got {len(opponents)}")
        return [(challenger,) + triple for triple in itertools.combinations(opponents, 3)]

    def _build_summary(self, matches: list[MatchResult]) -> dict:
        agent_stats: dict[str, dict] = {}
        total_duration = 0.0
        for m in matches:
            total_duration += m.duration_s
            for aid in m.agent_ids:
                stats = agent_stats.setdefault(
                    aid, {"wins": 0, "losses": 0, "draws": 0}
                )
                if m.winner is None:
                    stats["draws"] += 1
                elif m.winner == aid:
                    stats["wins"] += 1
                else:
                    stats["losses"] += 1
        return {
            "total_matches": len(matches),
            "total_duration_s": round(total_duration, 3),
            "agent_stats": agent_stats,
        }


# =========================================================================
# CLI
# =========================================================================


def _default_runs_dir() -> Path:
    return Path(os.environ.get("ORBIT_WARS_RUNS_DIR", "runs"))


def _default_zoo_dir() -> Path:
    return Path(os.environ.get("ORBIT_WARS_ZOO_DIR", "agents"))


def _cmd_list(args):
    zoo = scan_zoo(args.zoo)
    store = TrueSkillStore(args.runs / "trueskill.json")
    lb_2p = {r.agent_id: r for r in store.leaderboard(format="2p")}

    print(f"{'ID':<40}  {'BUCKET':<12}  {'μ':>6}  {'σ':>6}  {'N':>4}  TAGS")
    print("-" * 100)
    for a in zoo:
        r = lb_2p.get(a.id)
        mu = f"{r.mu:.0f}" if r else "-"
        sigma = f"{r.sigma:.0f}" if r else "-"
        games = str(r.games_played) if r else "0"
        tags = ",".join(a.tags) if a.tags else ""
        marker = " [disabled]" if a.disabled else ""
        print(f"{a.id:<40}  {a.bucket:<12}  {mu:>6}  {sigma:>6}  {games:>4}  {tags}{marker}")


def _cmd_show(args):
    zoo = scan_zoo(args.zoo)
    match = next((a for a in zoo if a.id == args.agent_id), None)
    if match is None:
        print(f"Agent {args.agent_id!r} not found in {args.zoo}", file=sys.stderr)
        sys.exit(1)
    print(f"ID:          {match.id}")
    print(f"Name:        {match.name}")
    print(f"Bucket:      {match.bucket}")
    print(f"Path:        {match.path}")
    print(f"Description: {match.description or '-'}")
    print(f"Author:      {match.author or '-'}")
    print(f"Kernel:      {match.kernel_slug or '-'}")
    print(f"Version:     {match.kernel_version if match.kernel_version else '-'}")
    print(f"License:     {match.license or '-'}")
    print(f"LB claim:    {match.author_claimed_lb_score if match.author_claimed_lb_score else '-'}")
    print(f"Fetched:     {match.date_fetched or '-'}")
    # DEPRECATED — only show when set, for backward compat
    if match.source_url:
        print(f"Source URL (DEPRECATED): {match.source_url}")
    if match.version:
        print(f"Version (DEPRECATED): {match.version}")
    print(f"Tags:        {', '.join(match.tags) if match.tags else '-'}")
    print(f"Disabled:    {match.disabled}")
    if match.last_error:
        print(f"Last error:  {match.last_error}")

    store = TrueSkillStore(args.runs / "trueskill.json")
    for fmt in ("2p", "4p"):
        r = store.get_rating(match.id, format=fmt)  # type: ignore[arg-type]
        print(f"Rating {fmt}:   μ={r.mu:.1f}  σ={r.sigma:.1f}  games={r.games_played}")


def _cmd_run(args):
    zoo = scan_zoo(args.zoo)
    agents = args.agents

    # Filter path 1: explicit --agents (list of IDs)
    if agents:
        # nothing — explicit list used as-is
        pass
    # Filter path 2: --bucket (comma-separated)
    elif args.bucket:
        buckets = set(args.bucket.split(","))
        filtered = [a for a in zoo if a.bucket in buckets]
        # Then apply tag filter ON TOP of bucket
        filtered = _filter_agents_by_tags(filtered, include=args.tag, exclude=args.exclude_tag)
        agents = [a.id for a in filtered]
    # Filter path 3: --tag / --exclude-tag (alone)
    elif args.tag or args.exclude_tag:
        filtered = _filter_agents_by_tags(zoo, include=args.tag, exclude=args.exclude_tag)
        agents = [a.id for a in filtered]
    # Filter path 4: none → all non-disabled
    else:
        agents = [a.id for a in zoo if not a.disabled]

    if not agents:
        print("No agents selected (check --agents / --bucket / --tag / --exclude-tag)", file=sys.stderr)
        sys.exit(1)
    min_agents = 4 if args.format == "4p" else 2
    if len(agents) < min_agents:
        print(
            f"Format {args.format} needs ≥{min_agents} agents, got {len(agents)}",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.parallel > 1:
        print(
            "--parallel >1 not yet implemented (Plan B feature); running sequentially.",
            file=sys.stderr,
        )
        args.parallel = 1

    args.runs.mkdir(parents=True, exist_ok=True)
    cfg = TournamentConfig(
        agents=agents,
        games_per_pair=args.games_per_pair,
        mode=args.mode,
        format=args.format,
        parallel=args.parallel,
        seed_base=args.seed,
    )
    t = Tournament(config=cfg, runs_root=args.runs, zoo_root=args.zoo)
    run_id = t.run()
    print(f"Run {run_id} completed → {args.runs / run_id}")


def _cmd_gauntlet(args):
    zoo = scan_zoo(args.zoo)
    challenger_id = args.challenger
    if not any(a.id == challenger_id and not a.disabled for a in zoo):
        print(f"Challenger {challenger_id!r} not found or disabled in zoo", file=sys.stderr)
        sys.exit(1)

    # Opponents: apply same filters as `run`, then make sure challenger is included.
    if args.agents:
        opponents = [aid for aid in args.agents if aid != challenger_id]
    elif args.bucket:
        buckets = [b.strip() for b in args.bucket.split(",") if b.strip()]
        filtered = [a for a in zoo if not a.disabled and a.bucket in buckets]
        filtered = _filter_agents_by_tags(filtered, include=args.tag, exclude=args.exclude_tag)
        opponents = [a.id for a in filtered if a.id != challenger_id]
    elif args.tag or args.exclude_tag:
        filtered = _filter_agents_by_tags(zoo, include=args.tag, exclude=args.exclude_tag)
        opponents = [a.id for a in filtered if a.id != challenger_id and not a.disabled]
    else:
        opponents = [a.id for a in zoo if not a.disabled and a.id != challenger_id]

    if not opponents:
        print("No opponents selected (check --agents / --bucket / --tag)", file=sys.stderr)
        sys.exit(1)
    min_opponents = 3 if args.format == "4p" else 1
    if len(opponents) < min_opponents:
        print(f"Format {args.format} gauntlet needs ≥{min_opponents} opponents, got {len(opponents)}",
              file=sys.stderr)
        sys.exit(1)

    args.runs.mkdir(parents=True, exist_ok=True)
    cfg = TournamentConfig(
        agents=[challenger_id] + opponents,
        games_per_pair=args.games_per_pair,
        mode=args.mode,
        format=args.format,
        seed_base=args.seed,
        shape="gauntlet",
        challenger_id=challenger_id,
    )
    t = Tournament(config=cfg, runs_root=args.runs, zoo_root=args.zoo)
    run_id = t.run()
    print(f"Gauntlet {challenger_id} vs {len(opponents)} opponents: run {run_id}")


def _cmd_head_to_head(args):
    args.runs.mkdir(parents=True, exist_ok=True)
    cfg = TournamentConfig(
        agents=[args.agent_a, args.agent_b],
        games_per_pair=args.games,
        mode=args.mode,
        format="2p",
        seed_base=args.seed,
    )
    t = Tournament(config=cfg, runs_root=args.runs, zoo_root=args.zoo)
    run_id = t.run()
    print(f"Head-to-head {args.agent_a} vs {args.agent_b}: run {run_id}")


def main():
    parser = argparse.ArgumentParser(
        prog="python -m orbit_wars_app.tournament",
        description="Orbit Wars Lab — local tournament runner",
    )
    parser.add_argument("--zoo", type=Path, default=_default_zoo_dir())
    parser.add_argument("--runs", type=Path, default=_default_runs_dir())
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="Show zoo + TrueSkill")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="Show agent details")
    p_show.add_argument("agent_id")
    p_show.set_defaults(func=_cmd_show)

    p_run = sub.add_parser("run", help="Run a tournament")
    p_run.add_argument("--agents", nargs="*", default=[], help="Explicit agent IDs")
    p_run.add_argument("--bucket", default="", help="Comma-separated buckets (baselines,external,mine)")
    p_run.add_argument(
        "--tag", action="append", default=[],
        help="Include agents with this tag (repeatable = OR). "
             "Example: --tag benchmark --tag quick → benchmark OR quick",
    )
    p_run.add_argument(
        "--exclude-tag", action="append", default=[], dest="exclude_tag",
        help="Exclude agents with this tag (repeatable = AND). "
             "Example: --exclude-tag broken --exclude-tag slow",
    )
    p_run.add_argument("--games-per-pair", type=int, default=3, help="K games per pair (default 3)")
    p_run.add_argument("--mode", choices=["fast", "faithful"], default="fast",
                       help="fast=in-process, faithful=subprocess+HTTP (Kaggle protocol)")
    p_run.add_argument("--format", choices=["2p", "4p"], default="2p",
                       help="Match format — 2-player or 4-player FFA (default 2p)")
    p_run.add_argument("--parallel", type=int, default=1, help="Parallel matches (fast mode only)")
    p_run.add_argument("--seed", type=int, default=42, help="Base seed for match randomness")
    p_run.set_defaults(func=_cmd_run)

    p_g = sub.add_parser("gauntlet", help="One challenger vs every other agent (× K games)")
    p_g.add_argument("challenger", help="Challenger agent ID (e.g. mine/v1-my-bot)")
    p_g.add_argument("--agents", nargs="*", default=[], help="Explicit opponent IDs (excludes challenger)")
    p_g.add_argument("--bucket", default="", help="Comma-separated buckets for opponents")
    p_g.add_argument("--tag", action="append", default=[], help="Include opponents with this tag")
    p_g.add_argument("--exclude-tag", action="append", default=[], dest="exclude_tag",
                     help="Exclude opponents with this tag")
    p_g.add_argument("--games-per-pair", type=int, default=10, help="K games per opponent (default 10)")
    p_g.add_argument("--mode", choices=["fast", "faithful"], default="fast")
    p_g.add_argument("--format", choices=["2p", "4p"], default="2p",
                     help="2p: challenger vs 1 opponent. 4p: challenger + 3 opponents per match.")
    p_g.add_argument("--seed", type=int, default=42)
    p_g.set_defaults(func=_cmd_gauntlet)

    p_h2h = sub.add_parser("head-to-head", help="N games between exactly two agents (always 2p)")
    p_h2h.add_argument("agent_a", help="First agent ID (player 0)")
    p_h2h.add_argument("agent_b", help="Second agent ID (player 1)")
    p_h2h.add_argument("--games", type=int, default=10, help="Number of games (default 10)")
    p_h2h.add_argument("--mode", choices=["fast", "faithful"], default="fast",
                       help="fast=in-process, faithful=subprocess+HTTP")
    p_h2h.add_argument("--seed", type=int, default=42, help="Base seed")
    p_h2h.set_defaults(func=_cmd_head_to_head)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
