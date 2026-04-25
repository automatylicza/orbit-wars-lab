"""Kaggle token management — read/write/validate ~/.kaggle/kaggle.json.

Used by the Settings tab in the viewer so users can wire up their own Kaggle
account without shell access. The token stays on the host machine: we write
it to the standard Kaggle CLI location (`$KAGGLE_CONFIG_DIR` or `~/.kaggle/`)
with mode 0o600 and never send it back to the frontend.

Validation notes
================
We avoid the Kaggle SDK for validating candidate tokens because the SDK reads
`KAGGLE_USERNAME`/`KAGGLE_KEY` env vars with **higher priority** than the
config file, which would let env vars "cheat" validation (user pastes wrong
token, SDK uses env vars instead, validation passes, later API calls break).
Direct HTTP against kaggle.com/api/v1 with Basic auth bypasses the SDK
entirely — deterministic and free of global mutable state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import requests


KAGGLE_API_ROOT = "https://www.kaggle.com/api/v1"
VALIDATE_TIMEOUT_SEC = 10.0


class KaggleAuthError(Exception):
    """Raised when token parsing, validation, or IO fails."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _config_dir() -> Path:
    """Match the Kaggle CLI's lookup order: $KAGGLE_CONFIG_DIR then ~/.kaggle."""
    override = os.environ.get("KAGGLE_CONFIG_DIR")
    if override:
        return Path(override)
    home = os.environ.get("HOME") or str(Path.home())
    return Path(home) / ".kaggle"


def _token_path() -> Path:
    return _config_dir() / "kaggle.json"


def get_status() -> dict:
    """Return {connected, username, source} without hitting the Kaggle API.

    Matches Kaggle SDK's resolution order: env vars first (they win at SDK
    authenticate time), then config file. If env vars are set, the file
    doesn't actually matter — so reporting that truthfully to the UI keeps
    the "Disconnect" affordance honest.

    `source` is one of "env" | "file" | None (when disconnected).
    """
    env_user = os.environ.get("KAGGLE_USERNAME", "").strip()
    env_key = os.environ.get("KAGGLE_KEY", "").strip()
    if env_user and env_key:
        return {"connected": True, "username": env_user, "source": "env"}

    path = _token_path()
    if not path.is_file():
        return {"connected": False, "username": None, "source": None}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"connected": False, "username": None, "source": None}
    username = data.get("username") if isinstance(data, dict) else None
    if not isinstance(username, str) or not username.strip():
        return {"connected": False, "username": None, "source": None}
    return {"connected": True, "username": username, "source": "file"}


def _is_bearer_token(key: str) -> bool:
    """Kaggle's new-style access tokens start with `KGAT_` and require Bearer
    auth (Authorization: Bearer ...) instead of Basic auth (username:key).

    The SDK reads them from `KAGGLE_API_TOKEN` env var; we keep them in the
    standard kaggle.json `key` field and set the env var at runtime via
    `apply_token_to_env()` before any SDK call.
    """
    return key.startswith("KGAT_")


def _resolve_bearer_username(access_token: str) -> str:
    """Look up the username for a bare KGAT_ access token via Kaggle's
    introspection endpoint. Used when the user pastes only the token (no JSON
    wrapper), since we still want to record `username` in kaggle.json so the
    rest of the codebase (Settings UI, scraper paths) keeps working.
    """
    try:
        from kagglesdk import KaggleClient, KaggleEnv  # type: ignore[attr-defined]
        from kagglesdk.security.types.oauth_api_service import IntrospectTokenRequest  # type: ignore[attr-defined]
    except ImportError as e:
        raise KaggleAuthError(500, f"kagglesdk not available for token introspection: {e}")
    try:
        with KaggleClient(env=KaggleEnv.PROD, verbose=False, access_token=access_token) as client:
            req = IntrospectTokenRequest()
            req.token = access_token
            resp = client.security.oauth_client.introspect_token(req)
    except Exception as e:
        raise KaggleAuthError(401, f"Could not introspect access token: {e}")
    username = getattr(resp, "username", None)
    if not getattr(resp, "active", False) or not isinstance(username, str) or not username.strip():
        raise KaggleAuthError(401, "Access token is inactive or has no associated username.")
    return username.strip()


def parse_token(raw: str) -> dict:
    """Parse a user-pasted token. Accepts:

    1. Full kaggle.json JSON: `{"username":"...","key":"..."}` (legacy 32-hex
       key OR new `KGAT_` access token in the `key` field).
    2. Bare access token starting with `KGAT_` — username is resolved via
       Kaggle's introspection endpoint.

    Two pitfalls to catch up front: (1) user pastes something like
    "my_username my_key" or similar free text — reject with guidance;
    (2) the file has extra fields we don't care about — accept but only
    keep username+key.
    """
    raw = (raw or "").strip()
    if not raw:
        raise KaggleAuthError(400, "Token is empty. Paste the contents of your kaggle.json file.")

    # Bare KGAT_ access token: Kaggle's new "API Token" UI displays just the
    # token string (no username), so accept it directly and look up username.
    if raw.startswith("KGAT_") and not raw.startswith("{"):
        username = _resolve_bearer_username(raw)
        return {"username": username, "key": raw}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise KaggleAuthError(
            400,
            f"Not valid JSON. Paste the full contents of kaggle.json (looks like "
            f'{{"username":"...","key":"..."}}) or a bare KGAT_ access token. '
            f"Parser said: {e.msg}",
        )
    if not isinstance(data, dict):
        raise KaggleAuthError(400, "Token must be a JSON object with username and key.")
    username = data.get("username")
    key = data.get("key")
    if not isinstance(username, str) or not username.strip():
        raise KaggleAuthError(400, "Missing or empty 'username' field.")
    if not isinstance(key, str) or not key.strip():
        raise KaggleAuthError(400, "Missing or empty 'key' field.")
    return {"username": username.strip(), "key": key.strip()}


def _validate_with_kaggle(username: str, key: str) -> None:
    """Round-trip the candidate token against kaggle.com/api/v1 directly.

    Bypasses the Kaggle SDK (which would consult env vars before our token),
    so what we test is exactly what was pasted — nothing else. Uses Bearer
    auth for new-style `KGAT_` access tokens, Basic auth for legacy 32-hex
    keys (https://www.kaggle.com/docs/api).
    """
    headers = {"User-Agent": "orbit-wars-lab/settings"}
    auth: Optional[tuple] = None
    if _is_bearer_token(key):
        headers["Authorization"] = f"Bearer {key}"
    else:
        auth = (username, key)
    try:
        response = requests.get(
            f"{KAGGLE_API_ROOT}/competitions/list",
            auth=auth,
            params={"search": "orbit-wars"},
            timeout=VALIDATE_TIMEOUT_SEC,
            headers=headers,
        )
    except requests.Timeout:
        raise KaggleAuthError(
            504,
            f"Kaggle API did not respond within {VALIDATE_TIMEOUT_SEC:.0f}s. "
            "Check your network and try again.",
        )
    except requests.RequestException as e:
        raise KaggleAuthError(502, f"Could not reach kaggle.com: {e}")

    if response.status_code == 401:
        raise KaggleAuthError(
            401,
            "Token rejected — username or key is wrong. "
            "Download a fresh kaggle.json from kaggle.com/settings/account.",
        )
    if response.status_code == 403:
        raise KaggleAuthError(
            403,
            "Token is valid, but you haven't joined the competition. "
            "Accept the rules at kaggle.com/competitions/orbit-wars/rules "
            "then retry.",
        )
    if response.status_code >= 400:
        # Surface Kaggle's own message when it's short and relevant; otherwise
        # fall back to status code so the UI doesn't render SDK internals.
        msg = (response.text or "").strip()
        if len(msg) > 200:
            msg = msg[:200] + "…"
        raise KaggleAuthError(
            response.status_code,
            f"Kaggle API returned {response.status_code}: {msg or 'no detail'}",
        )


def save_token(raw: str, *, validate: bool = True) -> dict:
    """Parse + validate + persist to $KAGGLE_CONFIG_DIR/kaggle.json.

    If `KAGGLE_USERNAME`/`KAGGLE_KEY` env vars are set, they shadow the file
    at SDK-read time — so we warn the caller (the UI then shows that env vars
    are the effective source).
    """
    parsed = parse_token(raw)
    if validate:
        _validate_with_kaggle(parsed["username"], parsed["key"])

    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    # Create the file already at 0o600 so there's no window where the token
    # sits on disk under the process umask (typically 0o644). os.open respects
    # the mode on creation (modulo umask); we also chmod after in case the file
    # already existed.
    payload = json.dumps(parsed).encode("utf-8")
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    except OSError:
        # Fallback for exotic filesystems (e.g. Windows bind mounts) that
        # reject POSIX flags — write plainly and chmod best-effort.
        path.write_text(json.dumps(parsed))
    else:
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
    try:
        path.chmod(0o600)
    except OSError:
        pass

    _invalidate_downstream_caches()

    status = get_status()
    # If env vars shadow the file, get_status reports source=env — flag it so
    # the UI can warn "file saved, but env vars will be used instead".
    if status["source"] == "env" and status["username"] != parsed["username"]:
        status["shadowed"] = True
        status["saved_username"] = parsed["username"]
    return status


def clear_token() -> dict:
    """Delete the config file. Does NOT touch env vars (we can't change the
    parent process's environment). Returns the fresh status so the UI can
    distinguish "truly disconnected" from "file gone but env vars still set".
    """
    path = _token_path()
    existed = path.is_file()
    if existed:
        try:
            path.unlink()
        except OSError as e:
            raise KaggleAuthError(500, f"Could not delete token file: {e}")
    _invalidate_downstream_caches()
    status = get_status()
    status["deleted"] = existed
    return status


def apply_token_to_env() -> None:
    """Bridge the on-disk kaggle.json to the SDK's runtime env-var contract.

    The Kaggle SDK 2.x routes new-style `KGAT_` access tokens through the
    `KAGGLE_API_TOKEN` environment variable (read by
    `_authenticate_with_access_token` → `get_access_token_from_env`), not
    through the legacy `key` field of kaggle.json (which goes through Basic
    auth and 401s on KGAT). To stay backwards-compatible we keep the token in
    kaggle.json's `key` field and lift it into the env var on demand.

    No-op for legacy 32-hex keys (Basic auth handles those natively), and
    no-op when env vars are already set (the user's shell wins by design —
    matches `get_status` reporting source=env).
    """
    if os.environ.get("KAGGLE_API_TOKEN", "").strip():
        return
    if os.environ.get("KAGGLE_USERNAME", "").strip() and os.environ.get("KAGGLE_KEY", "").strip():
        return
    path = _token_path()
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    key = data.get("key")
    if isinstance(key, str) and _is_bearer_token(key):
        os.environ["KAGGLE_API_TOKEN"] = key


def _invalidate_downstream_caches() -> None:
    """Drop any module-level caches that were authenticated against the old token."""
    try:
        from . import kaggle_submissions
    except ImportError:
        return
    cache = getattr(kaggle_submissions, "_submissions_cache", None)
    if isinstance(cache, dict):
        cache.clear()
