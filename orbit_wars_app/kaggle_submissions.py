"""Thin wrapper over the Kaggle Python API for submission + log data."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .schemas import KaggleSubmission


CACHE_TTL_SEC = 60.0


class KaggleCliError(Exception):
    """Raised when a Kaggle API call fails."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


_submissions_cache: dict[str, tuple[float, list[KaggleSubmission]]] = {}


def _get_api():
    """Return an authenticated KaggleApi instance.

    Imported lazily so the package's authentication doesn't run at module
    import time (package is chatty otherwise). Bridges KGAT_ access tokens
    from kaggle.json into the SDK-readable `KAGGLE_API_TOKEN` env var first,
    so SDK 2.x's `_authenticate_with_access_token` path picks them up.
    """
    from . import kaggle_auth
    kaggle_auth.apply_token_to_env()
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as e:
        raise KaggleCliError(500, f"kaggle package not installed: {e}")
    api = KaggleApi()
    try:
        api.authenticate()
    except Exception as e:
        raise KaggleCliError(401, f"Kaggle auth failed: {e}")
    return api


def _classify_api_error(exc: Exception) -> int:
    """Map kagglesdk / requests exception to an HTTP status code."""
    msg = str(exc).lower()
    if "401" in msg or "unauthorized" in msg:
        return 401
    if "403" in msg or "forbidden" in msg:
        return 403
    if "404" in msg or "not found" in msg:
        return 404
    return 500


def _convert_submission(raw) -> KaggleSubmission:
    """Convert an ApiSubmission object to our Pydantic model.

    `raw.ref` is the real integer submission ID from Kaggle.
    `raw.public_score` is a string decimal; may be empty for non-COMPLETE rows.
    """
    score = getattr(raw, "public_score", None)
    if score is None or str(score).strip() == "":
        mu = None
    else:
        try:
            mu = float(score)
        except (TypeError, ValueError):
            mu = None
    status = getattr(raw, "status", "") or ""
    status_str = getattr(status, "name", None) or str(status)
    return KaggleSubmission(
        submission_id=int(getattr(raw, "ref", 0)),
        description=str(getattr(raw, "description", "") or ""),
        date=str(getattr(raw, "date", "") or ""),
        status=status_str,
        mu=mu,
        sigma=None,
        rank=None,
        games_played=None,
    )


def list_my_submissions(competition: str = "orbit-wars") -> list[KaggleSubmission]:
    """List my submissions via Kaggle Python API. Cached for CACHE_TTL_SEC."""
    now = time.monotonic()
    cached = _submissions_cache.get(competition)
    if cached and (now - cached[0]) < CACHE_TTL_SEC:
        return cached[1]
    api = _get_api()
    try:
        raw = api.competition_submissions(competition)
    except Exception as e:
        code = _classify_api_error(e)
        raise KaggleCliError(code, str(e))
    subs = [_convert_submission(s) for s in raw]
    _submissions_cache[competition] = (now, subs)
    return subs


def submit_agent(
    file_path: Path, message: str, competition: str = "orbit-wars"
) -> dict:
    """Submit a .py file (or .tar.gz) to the competition. Invalidates list cache."""
    if not file_path.is_file():
        raise KaggleCliError(404, f"File not found: {file_path}")
    api = _get_api()
    try:
        resp = api.competition_submit(
            file_name=str(file_path),
            message=message,
            competition=competition,
            quiet=True,
        )
    except Exception as e:
        code = _classify_api_error(e)
        raise KaggleCliError(code, str(e))
    _submissions_cache.pop(competition, None)
    return {
        "ok": True,
        "message": getattr(resp, "message", None) or str(resp),
    }


def fetch_agent_logs(
    episode_id: int, agent_idx: int, cwd: Optional[Path] = None
) -> str:
    """Download my agent's stderr for one episode via the Kaggle Python API.

    Writes `episode-<ep>-agent-<idx>-logs.json` into `cwd` and returns its
    contents. The Kaggle CLI has no `competitions logs` subcommand; the feature
    is only reachable through `KaggleApi.competition_episode_agent_logs`.
    """
    work_dir = cwd or Path.cwd()
    work_dir.mkdir(parents=True, exist_ok=True)
    api = _get_api()
    try:
        api.competition_episode_agent_logs(
            episode_id=episode_id, agent_index=agent_idx, path=str(work_dir)
        )
    except KeyError as e:
        # kagglesdk's download_file raises KeyError('content-length') when the
        # response has no body (empty stderr). Treat as a clean 200 with "".
        if str(e).strip("'\"") == "content-length":
            return ""
        raise KaggleCliError(500, f"Unexpected KeyError: {e}")
    except Exception as e:
        code = _classify_api_error(e)
        raise KaggleCliError(code, str(e))
    log_path = work_dir / f"episode-{episode_id}-agent-{agent_idx}-logs.json"
    if not log_path.is_file():
        return ""
    return log_path.read_text()


def infer_my_agent_idx(
    submission_id: int, episode_id: int, replays_root: Path
) -> Optional[int]:
    """Look up the agent index of MY submission in a Kaggle episode.

    Reads `replays_root/kaggle/<submission_id>/_metadata.json` — a bulk snapshot
    written by the Kaggle scraper. Returns `None` if metadata is missing or
    does not mention my submission_id.
    """
    meta_path = replays_root / "kaggle" / str(submission_id) / "_metadata.json"
    if not meta_path.is_file():
        return None
    try:
        episodes = json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    for ep in episodes:
        try:
            if int(ep.get("id", 0)) != episode_id:
                continue
        except (TypeError, ValueError):
            continue
        for i, agent in enumerate(ep.get("agents", []) or []):
            if isinstance(agent, dict) and agent.get("submissionId") == submission_id:
                return i
    return None
