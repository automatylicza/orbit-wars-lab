"""Unit tests for orbit_wars_app.kaggle_auth."""
from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from orbit_wars_app import kaggle_auth as ka
from orbit_wars_app.kaggle_auth import KaggleAuthError


# ---------- parse_token ----------


def test_parse_token_happy_path():
    result = ka.parse_token('{"username":"alice","key":"abc123"}')
    assert result == {"username": "alice", "key": "abc123"}


def test_parse_token_strips_whitespace_and_newlines():
    """Users often paste with trailing newline — accept."""
    result = ka.parse_token('  {"username":"alice","key":"abc123"}\n\n')
    assert result["username"] == "alice"
    assert result["key"] == "abc123"


def test_parse_token_strips_values():
    """Stray spaces inside JSON strings shouldn't poison the saved file."""
    result = ka.parse_token('{"username":"  alice  ","key":"  abc123  "}')
    assert result == {"username": "alice", "key": "abc123"}


def test_parse_token_rejects_empty():
    with pytest.raises(KaggleAuthError) as exc:
        ka.parse_token("")
    assert exc.value.status_code == 400
    assert "empty" in exc.value.message.lower()


def test_parse_token_rejects_empty_whitespace():
    with pytest.raises(KaggleAuthError):
        ka.parse_token("   \n  \n")


def test_parse_token_rejects_non_json():
    with pytest.raises(KaggleAuthError) as exc:
        ka.parse_token("my_username my_key")
    assert exc.value.status_code == 400
    assert "json" in exc.value.message.lower()


def test_parse_token_rejects_non_object():
    """Arrays and scalars are valid JSON but not a token."""
    with pytest.raises(KaggleAuthError):
        ka.parse_token('["foo"]')
    with pytest.raises(KaggleAuthError):
        ka.parse_token('"just a string"')


def test_parse_token_rejects_missing_username():
    with pytest.raises(KaggleAuthError) as exc:
        ka.parse_token('{"key":"abc"}')
    assert "username" in exc.value.message.lower()


def test_parse_token_rejects_missing_key():
    with pytest.raises(KaggleAuthError) as exc:
        ka.parse_token('{"username":"alice"}')
    assert "key" in exc.value.message.lower()


def test_parse_token_rejects_empty_fields():
    with pytest.raises(KaggleAuthError):
        ka.parse_token('{"username":"","key":"abc"}')
    with pytest.raises(KaggleAuthError):
        ka.parse_token('{"username":"alice","key":""}')


def test_parse_token_accepts_extra_fields():
    """Kaggle sometimes adds proxy info fields — keep only what we need."""
    result = ka.parse_token(
        '{"username":"alice","key":"abc","proxy":"foo","other":123}'
    )
    assert result == {"username": "alice", "key": "abc"}


# ---------- get_status ----------


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """Point KAGGLE_CONFIG_DIR at tmp and wipe KAGGLE_USERNAME/KAGGLE_KEY so
    each test starts from a known blank slate regardless of host env."""
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    return tmp_path


def test_get_status_disconnected_when_no_file(isolated_config):
    assert ka.get_status() == {"connected": False, "username": None, "source": None}


def test_get_status_reports_file(isolated_config):
    (isolated_config / "kaggle.json").write_text(
        json.dumps({"username": "alice", "key": "abc"})
    )
    status = ka.get_status()
    assert status == {"connected": True, "username": "alice", "source": "file"}


def test_get_status_env_vars_win_over_file(isolated_config, monkeypatch):
    """Matches Kaggle SDK priority: env vars shadow the file."""
    (isolated_config / "kaggle.json").write_text(
        json.dumps({"username": "alice", "key": "abc"})
    )
    monkeypatch.setenv("KAGGLE_USERNAME", "bob")
    monkeypatch.setenv("KAGGLE_KEY", "xyz")
    status = ka.get_status()
    assert status == {"connected": True, "username": "bob", "source": "env"}


def test_get_status_env_partial_ignored(isolated_config, monkeypatch):
    """Only ONE of KAGGLE_USERNAME/KAGGLE_KEY set — SDK also treats as
    unusable, so we should too."""
    monkeypatch.setenv("KAGGLE_USERNAME", "bob")
    # no KAGGLE_KEY
    (isolated_config / "kaggle.json").write_text(
        json.dumps({"username": "alice", "key": "abc"})
    )
    assert ka.get_status()["source"] == "file"
    assert ka.get_status()["username"] == "alice"


def test_get_status_ignores_malformed_file(isolated_config):
    (isolated_config / "kaggle.json").write_text("not json at all {{")
    assert ka.get_status() == {"connected": False, "username": None, "source": None}


def test_get_status_ignores_file_without_username(isolated_config):
    (isolated_config / "kaggle.json").write_text(json.dumps({"key": "abc"}))
    assert ka.get_status()["connected"] is False


# ---------- save_token ----------


def test_save_token_writes_file_with_600_perms(isolated_config):
    with patch.object(ka, "_validate_with_kaggle"):
        ka.save_token('{"username":"alice","key":"abc"}')
    path = isolated_config / "kaggle.json"
    assert path.is_file()
    data = json.loads(path.read_text())
    assert data == {"username": "alice", "key": "abc"}
    # Permissions: owner-only (best-effort; some CI filesystems reject chmod
    # but on a real POSIX tmp_path this holds).
    mode = stat.S_IMODE(path.stat().st_mode)
    # Accept 0o600 (expected) or platforms that silently refuse chmod.
    assert mode in (0o600, path.stat().st_mode & 0o777)


def test_save_token_does_not_write_if_validation_fails(isolated_config):
    def fail(*a, **kw):
        raise KaggleAuthError(401, "nope")

    with patch.object(ka, "_validate_with_kaggle", side_effect=fail):
        with pytest.raises(KaggleAuthError):
            ka.save_token('{"username":"alice","key":"abc"}')
    assert not (isolated_config / "kaggle.json").exists()


def test_save_token_skips_validation_when_asked(isolated_config):
    # validate=False exists for tests; shouldn't call _validate
    with patch.object(ka, "_validate_with_kaggle") as spy:
        ka.save_token('{"username":"alice","key":"abc"}', validate=False)
        spy.assert_not_called()


def test_save_token_returns_status_with_file_source(isolated_config):
    with patch.object(ka, "_validate_with_kaggle"):
        status = ka.save_token('{"username":"alice","key":"abc"}')
    assert status["connected"] is True
    assert status["username"] == "alice"
    assert status["source"] == "file"


def test_save_token_flags_shadowed_when_env_vars_set(isolated_config, monkeypatch):
    """User pastes a file, but env vars are set — UI must know the saved file
    is not the active identity."""
    monkeypatch.setenv("KAGGLE_USERNAME", "bob")
    monkeypatch.setenv("KAGGLE_KEY", "xyz")
    with patch.object(ka, "_validate_with_kaggle"):
        status = ka.save_token('{"username":"alice","key":"abc"}')
    assert status["source"] == "env"
    assert status["username"] == "bob"
    assert status.get("shadowed") is True
    assert status.get("saved_username") == "alice"


# ---------- clear_token ----------


def test_clear_token_deletes_file(isolated_config):
    path = isolated_config / "kaggle.json"
    path.write_text(json.dumps({"username": "alice", "key": "abc"}))
    result = ka.clear_token()
    assert result["deleted"] is True
    assert result["connected"] is False
    assert not path.exists()


def test_clear_token_is_idempotent(isolated_config):
    """Calling clear when nothing exists shouldn't raise."""
    result = ka.clear_token()
    assert result["deleted"] is False
    assert result["connected"] is False


def test_clear_token_reports_env_vars_still_active(isolated_config, monkeypatch):
    """File gone but env vars set — status must stay connected (truthful UI)."""
    (isolated_config / "kaggle.json").write_text(
        json.dumps({"username": "alice", "key": "abc"})
    )
    monkeypatch.setenv("KAGGLE_USERNAME", "bob")
    monkeypatch.setenv("KAGGLE_KEY", "xyz")
    result = ka.clear_token()
    assert result["deleted"] is True
    assert result["connected"] is True
    assert result["source"] == "env"
    assert result["username"] == "bob"


# ---------- _validate_with_kaggle ----------


class _FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


def test_validate_accepts_200(monkeypatch):
    monkeypatch.setattr(
        ka.requests, "get", lambda *a, **kw: _FakeResponse(status_code=200)
    )
    ka._validate_with_kaggle("alice", "abc")  # no raise


def test_validate_rejects_401(monkeypatch):
    monkeypatch.setattr(
        ka.requests, "get", lambda *a, **kw: _FakeResponse(status_code=401)
    )
    with pytest.raises(KaggleAuthError) as exc:
        ka._validate_with_kaggle("alice", "wrong_key")
    assert exc.value.status_code == 401
    assert "rejected" in exc.value.message.lower()


def test_validate_rejects_403_with_rules_hint(monkeypatch):
    monkeypatch.setattr(
        ka.requests, "get", lambda *a, **kw: _FakeResponse(status_code=403)
    )
    with pytest.raises(KaggleAuthError) as exc:
        ka._validate_with_kaggle("alice", "abc")
    assert exc.value.status_code == 403
    assert "rules" in exc.value.message.lower()


def test_validate_handles_timeout(monkeypatch):
    def timeout_it(*a, **kw):
        raise ka.requests.Timeout()

    monkeypatch.setattr(ka.requests, "get", timeout_it)
    with pytest.raises(KaggleAuthError) as exc:
        ka._validate_with_kaggle("alice", "abc")
    assert exc.value.status_code == 504
    assert "did not respond" in exc.value.message.lower()


def test_validate_handles_network_error(monkeypatch):
    def conn_err(*a, **kw):
        raise ka.requests.ConnectionError("DNS fail")

    monkeypatch.setattr(ka.requests, "get", conn_err)
    with pytest.raises(KaggleAuthError) as exc:
        ka._validate_with_kaggle("alice", "abc")
    assert exc.value.status_code == 502


def test_validate_truncates_long_error_bodies(monkeypatch):
    """We don't want huge Kaggle error pages to flood our UI."""
    monkeypatch.setattr(
        ka.requests,
        "get",
        lambda *a, **kw: _FakeResponse(status_code=500, text="x" * 1000),
    )
    with pytest.raises(KaggleAuthError) as exc:
        ka._validate_with_kaggle("alice", "abc")
    # Truncation adds … so message is ≤ ~250 chars regardless of Kaggle's body
    assert len(exc.value.message) < 250


# ---------- KGAT_ access tokens (new-style bearer) ----------


_KGAT_FAKE = "KGAT_" + "0" * 32  # Synthetic — never a real Kaggle token.


def test_is_bearer_token_recognizes_kgat_prefix():
    assert ka._is_bearer_token(_KGAT_FAKE) is True
    assert ka._is_bearer_token("32_hex_legacy_key_aaaaaaaaaaaaaa") is False
    assert ka._is_bearer_token("") is False


def test_parse_token_accepts_json_with_kgat_key():
    """JSON wrapper around KGAT_ should not trigger introspection — the
    pasted username is taken at face value, just like for legacy keys."""
    result = ka.parse_token(f'{{"username":"alice","key":"{_KGAT_FAKE}"}}')
    assert result == {"username": "alice", "key": _KGAT_FAKE}


def test_parse_token_bare_kgat_introspects(monkeypatch):
    """Bare KGAT_ string with no JSON wrapper — username is resolved by the
    Kaggle introspection endpoint so the rest of the codebase still has a
    username to work with."""
    monkeypatch.setattr(ka, "_resolve_bearer_username", lambda token: "alice")
    result = ka.parse_token(_KGAT_FAKE)
    assert result == {"username": "alice", "key": _KGAT_FAKE}


def test_parse_token_bare_kgat_introspect_failure_raises(monkeypatch):
    """Introspection 401 should surface as KaggleAuthError so the UI shows it
    rather than letting the SDK explode later."""
    def boom(_token: str) -> str:
        raise KaggleAuthError(401, "Access token is inactive.")

    monkeypatch.setattr(ka, "_resolve_bearer_username", boom)
    with pytest.raises(KaggleAuthError) as exc:
        ka.parse_token(_KGAT_FAKE)
    assert exc.value.status_code == 401


def test_parse_token_kgat_inside_json_doesnt_introspect(monkeypatch):
    """If user already pasted JSON, even with a KGAT_ key we trust the
    username field — never call the introspection endpoint."""
    sentinel = {"called": False}

    def boom(_token: str) -> str:
        sentinel["called"] = True
        return "should_not_happen"

    monkeypatch.setattr(ka, "_resolve_bearer_username", boom)
    result = ka.parse_token(f'{{"username":"alice","key":"{_KGAT_FAKE}"}}')
    assert result["username"] == "alice"
    assert sentinel["called"] is False


# ---------- _validate_with_kaggle: Bearer vs Basic ----------


class _SpyResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


def test_validate_kgat_uses_bearer_header(monkeypatch):
    """KGAT_ token must travel as Authorization: Bearer (not Basic auth) —
    Kaggle's API returns 401 for KGAT via Basic."""
    captured: dict = {}

    def fake_get(url, **kwargs):
        captured["auth"] = kwargs.get("auth")
        captured["headers"] = kwargs.get("headers", {})
        return _SpyResponse(status_code=200)

    monkeypatch.setattr(ka.requests, "get", fake_get)
    ka._validate_with_kaggle("alice", _KGAT_FAKE)
    assert captured["auth"] is None
    assert captured["headers"].get("Authorization") == f"Bearer {_KGAT_FAKE}"


def test_validate_legacy_uses_basic_auth(monkeypatch):
    """Legacy 32-hex tokens must continue to use Basic auth — backward compat."""
    captured: dict = {}

    def fake_get(url, **kwargs):
        captured["auth"] = kwargs.get("auth")
        captured["headers"] = kwargs.get("headers", {})
        return _SpyResponse(status_code=200)

    monkeypatch.setattr(ka.requests, "get", fake_get)
    ka._validate_with_kaggle("alice", "0123456789abcdef" * 2)
    assert captured["auth"] == ("alice", "0123456789abcdef" * 2)
    assert "Authorization" not in captured["headers"]


# ---------- apply_token_to_env: bridge KGAT into SDK env var ----------


def test_apply_token_to_env_sets_var_for_kgat(isolated_config, monkeypatch):
    """KGAT_ in kaggle.json is invisible to the SDK's Basic-auth code path —
    apply_token_to_env must lift it into KAGGLE_API_TOKEN so the SDK's
    access-token path can authenticate."""
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    (isolated_config / "kaggle.json").write_text(
        json.dumps({"username": "alice", "key": _KGAT_FAKE})
    )
    ka.apply_token_to_env()
    import os
    assert os.environ.get("KAGGLE_API_TOKEN") == _KGAT_FAKE


def test_apply_token_to_env_skip_for_legacy(isolated_config, monkeypatch):
    """Legacy 32-hex keys go through Basic auth — env var must stay unset to
    avoid the SDK picking the wrong code path."""
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    (isolated_config / "kaggle.json").write_text(
        json.dumps({"username": "alice", "key": "0123456789abcdef" * 2})
    )
    ka.apply_token_to_env()
    import os
    assert "KAGGLE_API_TOKEN" not in os.environ


def test_apply_token_to_env_respects_existing_env_var(isolated_config, monkeypatch):
    """User-supplied KAGGLE_API_TOKEN must win over the file (matches the
    SDK's own resolution order — env vars are the source of truth)."""
    monkeypatch.setenv("KAGGLE_API_TOKEN", "user_supplied_token")
    (isolated_config / "kaggle.json").write_text(
        json.dumps({"username": "alice", "key": _KGAT_FAKE})
    )
    ka.apply_token_to_env()
    import os
    assert os.environ["KAGGLE_API_TOKEN"] == "user_supplied_token"


def test_apply_token_to_env_skip_when_user_key_env_set(isolated_config, monkeypatch):
    """KAGGLE_USERNAME + KAGGLE_KEY shadow the file at SDK-read time, so we
    must not blow them away by injecting a bridged token."""
    monkeypatch.setenv("KAGGLE_USERNAME", "bob")
    monkeypatch.setenv("KAGGLE_KEY", "xyz")
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    (isolated_config / "kaggle.json").write_text(
        json.dumps({"username": "alice", "key": _KGAT_FAKE})
    )
    ka.apply_token_to_env()
    import os
    assert "KAGGLE_API_TOKEN" not in os.environ


def test_apply_token_to_env_no_file_is_noop(isolated_config, monkeypatch):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    ka.apply_token_to_env()
    import os
    assert "KAGGLE_API_TOKEN" not in os.environ


def test_apply_token_to_env_malformed_file_is_noop(isolated_config, monkeypatch):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    (isolated_config / "kaggle.json").write_text("not json")
    ka.apply_token_to_env()
    import os
    assert "KAGGLE_API_TOKEN" not in os.environ


# ---------- end-to-end smoke: save → get_status → clear → get_status ----------


def test_roundtrip(isolated_config):
    with patch.object(ka, "_validate_with_kaggle"):
        ka.save_token('{"username":"alice","key":"abc"}')
    assert ka.get_status()["username"] == "alice"
    ka.clear_token()
    assert ka.get_status()["connected"] is False
