"""Scan agents/ tree and return AgentInfo list."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import get_args

import yaml

from .schemas import AgentInfo, Bucket


_log = logging.getLogger(__name__)

_DEPRECATED_FIELDS = ("source_url", "version")

VALID_BUCKETS = set(get_args(Bucket))  # {"baselines", "external", "mine"}


def scan_zoo(zoo_dir: Path) -> list[AgentInfo]:
    """Return sorted list of agents found under zoo_dir/{bucket}/<name>/main.py.

    Buckets outside baselines/external/mine are ignored.
    Agents without main.py are ignored.
    Broken agent.yaml falls back to folder name, sets last_error.
    """
    agents: list[AgentInfo] = []
    if not zoo_dir.exists():
        return agents

    for bucket_dir in sorted(zoo_dir.iterdir()):
        if not bucket_dir.is_dir():
            continue
        bucket = bucket_dir.name
        if bucket not in VALID_BUCKETS:
            continue
        for agent_dir in sorted(bucket_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            main_py = agent_dir / "main.py"
            if not main_py.is_file():
                continue
            info = _build_agent_info(bucket, agent_dir, zoo_dir)
            agents.append(info)
    return agents


def _build_agent_info(bucket: str, agent_dir: Path, zoo_dir: Path) -> AgentInfo:
    folder_name = agent_dir.name
    agent_id = f"{bucket}/{folder_name}"
    rel_path = str(agent_dir.relative_to(zoo_dir.parent)).replace("\\", "/")

    yaml_path = agent_dir / "agent.yaml"
    yaml_data: dict = {}
    last_error: str | None = None
    has_yaml = yaml_path.is_file()

    if has_yaml:
        try:
            with yaml_path.open("r", encoding="utf-8") as f:
                parsed = yaml.safe_load(f)
            if parsed is None:
                yaml_data = {}
            elif isinstance(parsed, dict):
                yaml_data = parsed
            else:
                last_error = f"agent.yaml is not a mapping (got {type(parsed).__name__})"
        except yaml.YAMLError as e:
            last_error = f"yaml parse error: {e}"

    raw_tags = yaml_data.get("tags")
    if raw_tags is None:
        tags: list[str] = []
    elif isinstance(raw_tags, list):
        tags = [str(t) for t in raw_tags]
    else:
        tags = []
        if last_error is None:
            last_error = f"tags field is not a list (got {type(raw_tags).__name__})"

    # Warning log dla deprecated fields
    for dep_field in _DEPRECATED_FIELDS:
        if dep_field in yaml_data:
            _log.warning(
                "Agent %s uses deprecated field '%s' in agent.yaml; "
                "see docs/superpowers/specs/2026-04-21-agent-zoo-design.md",
                agent_id, dep_field,
            )

    # Parse kernel_version as int if present
    kv = yaml_data.get("kernel_version")
    kernel_version: int | None = None
    if kv is not None:
        try:
            kernel_version = int(kv)
        except (TypeError, ValueError):
            if last_error is None:
                last_error = f"kernel_version is not int (got {type(kv).__name__}: {kv!r})"

    # Parse author_claimed_lb_score as float if present
    alb = yaml_data.get("author_claimed_lb_score")
    author_claimed_lb_score: float | None = None
    if alb is not None:
        try:
            author_claimed_lb_score = float(alb)
        except (TypeError, ValueError):
            if last_error is None:
                last_error = f"author_claimed_lb_score is not float (got {type(alb).__name__}: {alb!r})"

    return AgentInfo(
        id=agent_id,
        name=yaml_data.get("name") or folder_name,
        bucket=bucket,  # type: ignore[arg-type]
        description=yaml_data.get("description"),
        author=yaml_data.get("author"),
        tags=tags,
        disabled=bool(yaml_data.get("disabled", False)),
        has_yaml=has_yaml,
        path=rel_path,
        last_error=last_error,
        # New fields
        kernel_slug=yaml_data.get("kernel_slug"),
        kernel_version=kernel_version,
        date_fetched=str(yaml_data["date_fetched"]) if "date_fetched" in yaml_data else None,
        license=yaml_data.get("license"),
        author_claimed_lb_score=author_claimed_lb_score,
        # Deprecated fields (backward compat)
        source_url=yaml_data.get("source_url"),
        version=str(yaml_data["version"]) if "version" in yaml_data else None,
    )
