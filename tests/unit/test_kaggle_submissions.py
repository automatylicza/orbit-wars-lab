"""Unit tests for orbit_wars_app.kaggle_submissions."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from orbit_wars_app import kaggle_submissions as ks
from orbit_wars_app.kaggle_submissions import KaggleCliError


def _fake_submission(**kw) -> SimpleNamespace:
    """Build an ApiSubmission-shaped duck typed object for tests."""
    defaults = dict(
        ref=0,
        description="",
        date="2026-04-20T00:00:00",
        status="COMPLETE",
        public_score="",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class _FakeApi:
    """Minimal stand-in for kaggle.api.kaggle_api_extended.KaggleApi."""

    def __init__(
        self,
        items=None,
        auth_raises=False,
        list_raises=None,
        logs_side_effect=None,
        logs_raises=None,
    ):
        self._items = items or []
        self._auth_raises = auth_raises
        self._list_raises = list_raises
        self._logs_side_effect = logs_side_effect
        self._logs_raises = logs_raises
        self.calls = 0

    def authenticate(self):
        if self._auth_raises:
            raise RuntimeError("auth failed")

    def competition_submissions(self, competition):
        self.calls += 1
        if self._list_raises:
            raise self._list_raises
        return self._items

    def competition_episode_agent_logs(self, *, episode_id, agent_index, path, quiet=True):
        if self._logs_raises:
            raise self._logs_raises
        if self._logs_side_effect:
            self._logs_side_effect(episode_id, agent_index, path)


def _install_fake_api(monkeypatch, fake):
    """Patch _get_api to return `fake` without triggering real kaggle imports."""
    monkeypatch.setattr(ks, "_get_api", lambda: fake)
    return fake


def test_list_my_submissions_happy(monkeypatch):
    ks._submissions_cache.clear()
    fake = _FakeApi(
        items=[
            _fake_submission(
                ref=51799179,
                description="v1-my-bot",
                date="2026-04-20T12:34:56",
                status="COMPLETE",
                public_score="742.3",
            ),
            _fake_submission(
                ref=51754321,
                description="v0-baseline",
                date="2026-04-18T09:00:00",
                status="COMPLETE",
                public_score="611.0",
            ),
        ]
    )
    _install_fake_api(monkeypatch, fake)
    result = ks.list_my_submissions(competition="orbit-wars")
    assert len(result) == 2
    assert result[0].submission_id == 51799179
    assert result[0].description == "v1-my-bot"
    assert result[0].mu == 742.3
    assert result[0].status == "COMPLETE"


def test_list_my_submissions_empty(monkeypatch):
    ks._submissions_cache.clear()
    fake = _FakeApi(items=[])
    _install_fake_api(monkeypatch, fake)
    assert ks.list_my_submissions() == []


def test_list_my_submissions_missing_public_score(monkeypatch):
    """FAILED rows may have empty public_score — mu must be None, not 0.0."""
    ks._submissions_cache.clear()
    fake = _FakeApi(
        items=[
            _fake_submission(
                ref=42,
                description="broken",
                status="FAILED",
                public_score="",
            )
        ]
    )
    _install_fake_api(monkeypatch, fake)
    result = ks.list_my_submissions()
    assert len(result) == 1
    assert result[0].mu is None
    assert result[0].status == "FAILED"
    assert result[0].submission_id == 42


def test_list_my_submissions_auth_fail(monkeypatch):
    ks._submissions_cache.clear()

    def boom():
        raise KaggleCliError(401, "Kaggle auth failed: token expired")

    monkeypatch.setattr(ks, "_get_api", boom)
    with pytest.raises(KaggleCliError) as exc:
        ks.list_my_submissions()
    assert exc.value.status_code == 401


def test_list_my_submissions_api_403(monkeypatch):
    """Non-auth API errors are classified by _classify_api_error."""
    ks._submissions_cache.clear()
    fake = _FakeApi(list_raises=RuntimeError("403 Forbidden"))
    _install_fake_api(monkeypatch, fake)
    with pytest.raises(KaggleCliError) as exc:
        ks.list_my_submissions()
    assert exc.value.status_code == 403


def test_list_my_submissions_cached(monkeypatch):
    """Second call within TTL uses cache — API not called again."""
    ks._submissions_cache.clear()
    fake = _FakeApi(items=[_fake_submission(ref=1, description="x")])
    _install_fake_api(monkeypatch, fake)
    ks.list_my_submissions()
    ks.list_my_submissions()
    assert fake.calls == 1


# =========================
# _get_api: KGAT bridge
# =========================


def test_get_api_bridges_kgat_into_env(monkeypatch, tmp_path):
    """KGAT_ keys live in kaggle.json's `key` field (so the Settings flow can
    save/restore them like legacy tokens). The Kaggle SDK 2.x reads them only
    from KAGGLE_API_TOKEN env var, so _get_api must lift the file value into
    the env before calling authenticate()."""
    import os
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    (tmp_path / "kaggle.json").write_text(
        json.dumps({"username": "alice", "key": "KGAT_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
    )

    captured = {}

    class _StubApi:
        def authenticate(self):
            captured["env"] = os.environ.get("KAGGLE_API_TOKEN")

    # Patch the lazy import target inside _get_api.
    import sys
    import types as _types
    fake_mod = _types.ModuleType("kaggle.api.kaggle_api_extended")
    fake_mod.KaggleApi = _StubApi
    monkeypatch.setitem(sys.modules, "kaggle.api.kaggle_api_extended", fake_mod)

    ks._get_api()
    assert captured["env"] == "KGAT_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


# =========================
# fetch_agent_logs tests
# =========================

from pathlib import Path


def test_fetch_agent_logs_happy(monkeypatch, tmp_path):
    """API writes an `episode-<ep>-agent-<idx>-logs.json` file to path; wrapper reads it back."""
    log_text = "turn 23: WARN fleet=12 ignored sun\nturn 47: ERROR KeyError\n"

    def write_log(episode_id, agent_index, path):
        (Path(path) / f"episode-{episode_id}-agent-{agent_index}-logs.json").write_text(log_text)

    fake = _FakeApi(logs_side_effect=write_log)
    _install_fake_api(monkeypatch, fake)

    text = ks.fetch_agent_logs(episode_id=70123456, agent_idx=0, cwd=tmp_path)
    assert "ERROR KeyError" in text


def test_fetch_agent_logs_403(monkeypatch, tmp_path):
    fake = _FakeApi(logs_raises=RuntimeError("403 Forbidden"))
    _install_fake_api(monkeypatch, fake)
    with pytest.raises(KaggleCliError) as exc:
        ks.fetch_agent_logs(episode_id=70123456, agent_idx=1, cwd=tmp_path)
    assert exc.value.status_code == 403


def test_fetch_agent_logs_no_file_written(monkeypatch, tmp_path):
    """API call succeeded but didn't write a log file — return empty string."""
    fake = _FakeApi()  # default: logs_side_effect is None → no file written
    _install_fake_api(monkeypatch, fake)
    text = ks.fetch_agent_logs(episode_id=999, agent_idx=0, cwd=tmp_path)
    assert text == ""


# =========================
# infer_my_agent_idx tests
# =========================


def _write_metadata(sub_dir: Path, episodes: list):
    import json
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "_metadata.json").write_text(json.dumps(episodes))


def test_infer_idx_found(tmp_path):
    sub_dir = tmp_path / "kaggle" / "51799179"
    _write_metadata(
        sub_dir,
        [
            {
                "id": 70123456,
                "agents": [
                    {"submissionId": 99999999},
                    {"submissionId": 51799179},
                ],
            }
        ],
    )
    idx = ks.infer_my_agent_idx(
        submission_id=51799179, episode_id=70123456, replays_root=tmp_path
    )
    assert idx == 1


def test_infer_idx_not_in_metadata(tmp_path):
    sub_dir = tmp_path / "kaggle" / "51799179"
    _write_metadata(
        sub_dir,
        [{"id": 70123456, "agents": [{"submissionId": 88}, {"submissionId": 99}]}],
    )
    assert ks.infer_my_agent_idx(51799179, 70123456, tmp_path) is None


def test_infer_idx_no_metadata_file(tmp_path):
    assert ks.infer_my_agent_idx(51799179, 70123456, tmp_path) is None
