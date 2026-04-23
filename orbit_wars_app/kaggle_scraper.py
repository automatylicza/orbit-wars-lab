"""Kaggle Episode Scraper — wrapper for internal EpisodeService endpoints.

Integrates `refs/external-tools/episode-scraper/main.py` into the app.
Downloads episode metadata + replay JSON for a given submission_id.

Storage layout:
    replays/kaggle/<submission_id>/_metadata.json  — list of episodes
    replays/kaggle/<submission_id>/episode_<id>.json  — replay payload

No authentication required — endpoints accept anonymous requests.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests


logger = logging.getLogger(__name__)

KAGGLE_API_I_BASE = "https://www.kaggle.com/api/i"
LIST_EPISODES_ENDPOINT = f"{KAGGLE_API_I_BASE}/competitions.EpisodeService/ListEpisodes"
GET_REPLAY_ENDPOINT = f"{KAGGLE_API_I_BASE}/competitions.EpisodeService/GetEpisodeReplay"


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Content-Type": "application/json",
            "User-Agent": "orbit-wars-lab-scraper/1.0",
        }
    )
    return session


def _post_json(
    session: requests.Session, endpoint: str, payload: dict, timeout: int
) -> dict:
    response = session.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def list_episodes(session: requests.Session, submission_id: int) -> list[dict]:
    """Fetch episode list for a submission. Raises on HTTP error."""
    data = _post_json(
        session=session,
        endpoint=LIST_EPISODES_ENDPOINT,
        payload={"submissionId": submission_id},
        timeout=30,
    )
    return data.get("episodes", [])


def fetch_replay(session: requests.Session, episode_id: int) -> dict:
    """Fetch full replay payload for an episode."""
    return _post_json(
        session=session,
        endpoint=GET_REPLAY_ENDPOINT,
        payload={"episodeId": episode_id},
        timeout=60,
    )


# ============================================================
# Job tracking for async scrape (POST /api/replays/scrape)
# ============================================================

@dataclass
class ScrapeJob:
    job_id: str
    submission_id: int
    count: int
    status: str = "pending"  # pending | running | completed | failed
    total: int = 0
    downloaded: int = 0
    error: Optional[str] = None
    replay_ids: list[int] = field(default_factory=list)


_jobs: dict[str, ScrapeJob] = {}
_jobs_lock = threading.Lock()


def get_job(job_id: str) -> Optional[ScrapeJob]:
    with _jobs_lock:
        return _jobs.get(job_id)


def _kaggle_root(replays_root: Path) -> Path:
    return replays_root / "kaggle"


def scrape_submission(
    submission_id: int,
    count: int,
    replays_root: Path,
    job_id: Optional[str] = None,
) -> ScrapeJob:
    """Synchronously scrape `count` episodes for `submission_id`.

    Writes to `replays_root/kaggle/<submission_id>/`. Updates job state
    if job_id is given (for background dispatch).

    Returns the ScrapeJob with final state.
    """
    job = ScrapeJob(
        job_id=job_id or uuid.uuid4().hex,
        submission_id=submission_id,
        count=count,
    )
    with _jobs_lock:
        _jobs[job.job_id] = job

    try:
        job.status = "running"
        session = _build_session()

        out_dir = _kaggle_root(replays_root) / str(submission_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Listing episodes for submission %s", submission_id)
        episodes = list_episodes(session, submission_id)
        logger.info("Got %d episodes; will download up to %d", len(episodes), count)

        # Write metadata snapshot (list of all episodes available)
        (out_dir / "_metadata.json").write_text(
            json.dumps(episodes, indent=2), encoding="utf-8"
        )

        to_download = episodes[: max(0, count)]
        job.total = len(to_download)

        for ep in to_download:
            ep_id = int(ep.get("id"))
            replay_path = out_dir / f"episode_{ep_id}.json"
            if replay_path.exists():
                job.downloaded += 1
                job.replay_ids.append(ep_id)
                continue
            try:
                payload = fetch_replay(session, ep_id)
                replay_path.write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                job.downloaded += 1
                job.replay_ids.append(ep_id)
            except Exception as e:
                logger.warning("Failed to fetch episode %s: %s", ep_id, e)
                continue

        job.status = "completed"
        return job
    except Exception as e:
        logger.exception("Scrape job %s failed", job.job_id)
        job.status = "failed"
        job.error = str(e)
        return job


def _extract_meta(payload: dict, episode_id: int) -> dict:
    """Extract lightweight metadata from a Kaggle replay payload for listing.

    Kaggle replay JSON is ~2 MB; we don't want to re-parse it on every list
    request. This function distills the fields we show in the UI.
    """
    info = payload.get("info", {}) if isinstance(payload, dict) else {}
    agents = info.get("Agents", []) or []
    team_names = info.get("TeamNames", []) or [a.get("Name") for a in agents]
    rewards = payload.get("rewards", []) if isinstance(payload, dict) else []

    winner_idx: Optional[int] = None
    if rewards and any(r is not None for r in rewards):
        try:
            winner_idx = max(
                range(len(rewards)),
                key=lambda i: rewards[i] if rewards[i] is not None else float("-inf"),
            )
        except ValueError:
            winner_idx = None

    return {
        "episode_id": episode_id,
        "agents": [{"name": a.get("Name")} for a in agents],
        "team_names": team_names,
        "rewards": rewards,
        "winner_idx": winner_idx,
        "winner": team_names[winner_idx] if winner_idx is not None and winner_idx < len(team_names) else None,
    }


def scrape_single_episode(
    episode_id: int,
    submission_id: int,
    replays_root: Path,
) -> Path:
    """Fetch one replay by episode_id and write to disk.

    Storage:
      replays/kaggle/<submission_id>/episode_<episode_id>.json       — full replay
      replays/kaggle/<submission_id>/episode_<episode_id>.meta.json  — skinny list metadata

    submission_id used only for folder grouping; pass 0 / sentinel if unknown.

    Returns path to the full replay file. Raises on network error.
    """
    session = _build_session()
    out_dir = _kaggle_root(replays_root) / str(submission_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    replay_path = out_dir / f"episode_{episode_id}.json"
    meta_path = out_dir / f"episode_{episode_id}.meta.json"

    if replay_path.exists() and meta_path.exists():
        return replay_path

    if replay_path.exists():
        # Rebuild meta from existing replay
        payload = json.loads(replay_path.read_text())
    else:
        payload = fetch_replay(session, episode_id)
        replay_path.write_text(json.dumps(payload), encoding="utf-8")

    meta_path.write_text(json.dumps(_extract_meta(payload, episode_id), indent=2))
    return replay_path


def list_local_kaggle_replays(replays_root: Path) -> list[dict]:
    """Scan replays/kaggle/ and return metadata for all downloaded replays.

    Prefers per-episode .meta.json (written at scrape time, cheap to read).
    Falls back to per-submission _metadata.json (bulk ListEpisodes snapshot).
    Last resort: opens the full replay JSON to extract agent names — slow
    but ensures UI never shows "?".

    Returns list of dicts:
        {
          "source": "kaggle",
          "submission_id": int,
          "episode_id": int,
          "path": str (relative to project root),
          "agents": [{"name": "..."}],
          "team_names": [...],
          "winner": "...",
          "type": "...",
          "endTime": "...",
        }
    """
    root = _kaggle_root(replays_root)
    if not root.is_dir():
        return []

    result: list[dict] = []
    for sub_dir in sorted(root.iterdir()):
        if not sub_dir.is_dir():
            continue
        submission_id_str = sub_dir.name
        try:
            submission_id = int(submission_id_str)
        except ValueError:
            continue

        # Per-submission metadata (from ListEpisodes) if present
        bulk_meta_path = sub_dir / "_metadata.json"
        bulk_by_id: dict[int, dict] = {}
        if bulk_meta_path.is_file():
            try:
                episodes = json.loads(bulk_meta_path.read_text())
                for ep in episodes:
                    bulk_by_id[int(ep["id"])] = ep
            except Exception:
                pass

        for replay_file in sorted(sub_dir.glob("episode_*.json")):
            if replay_file.name.endswith(".meta.json"):
                continue
            try:
                ep_id = int(replay_file.stem.replace("episode_", ""))
            except ValueError:
                continue
            entry = {
                "source": "kaggle",
                "submission_id": submission_id,
                "episode_id": ep_id,
                "path": str(replay_file.relative_to(replays_root.parent)),
                "ts": replay_file.stat().st_mtime,
            }

            # 1. Per-episode meta (cheap)
            meta_path = sub_dir / f"episode_{ep_id}.meta.json"
            if meta_path.is_file():
                try:
                    m = json.loads(meta_path.read_text())
                    entry["agents"] = m.get("agents", [])
                    entry["team_names"] = m.get("team_names", [])
                    entry["winner"] = m.get("winner")
                except Exception:
                    pass

            # 2. Bulk metadata fill-in (type/endTime still useful)
            if ep_id in bulk_by_id:
                meta = bulk_by_id[ep_id]
                entry.setdefault("agents", meta.get("agents", []))
                entry["type"] = meta.get("type")
                entry["endTime"] = meta.get("endTime")

            # 3. Last-resort fallback: parse replay and backfill meta (once)
            if "agents" not in entry or not entry["agents"]:
                try:
                    payload = json.loads(replay_file.read_text())
                    m = _extract_meta(payload, ep_id)
                    entry["agents"] = m["agents"]
                    entry["team_names"] = m["team_names"]
                    entry["winner"] = m["winner"]
                    # Write meta so next call is cheap
                    meta_path.write_text(json.dumps(m, indent=2))
                except Exception:
                    pass

            result.append(entry)

    return result
