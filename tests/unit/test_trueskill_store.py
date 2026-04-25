"""Tests for orbit_wars_app.trueskill_store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orbit_wars_app.trueskill_store import (
    TrueSkillStore,
    TS_MU_0,
    TS_SIGMA_0,
)


def test_fresh_agent_has_default_rating(tmp_path: Path):
    store = TrueSkillStore(tmp_path / "trueskill.json")
    rating = store.get_rating("mine/new-bot", format="2p")
    assert rating.mu == TS_MU_0
    assert rating.sigma == TS_SIGMA_0
    assert rating.games_played == 0


def test_update_changes_mu(tmp_path: Path):
    store = TrueSkillStore(tmp_path / "trueskill.json")

    store.update_match(
        agent_ids=["a/x", "b/y"], winner="a/x", format="2p"
    )

    ra = store.get_rating("a/x", format="2p")
    rb = store.get_rating("b/y", format="2p")
    assert ra.mu > TS_MU_0
    assert rb.mu < TS_MU_0
    assert ra.games_played == 1
    assert rb.games_played == 1


def test_update_draw_keeps_mu_close(tmp_path: Path):
    store = TrueSkillStore(tmp_path / "trueskill.json")

    store.update_match(
        agent_ids=["a/x", "b/y"], winner=None, format="2p"
    )

    ra = store.get_rating("a/x", format="2p")
    rb = store.get_rating("b/y", format="2p")
    # Draw between equal agents → μ unchanged (symmetric)
    assert ra.mu == pytest.approx(rb.mu, abs=0.5)


def test_persistence_roundtrip(tmp_path: Path):
    path = tmp_path / "trueskill.json"

    store = TrueSkillStore(path)
    store.update_match(agent_ids=["a/x", "b/y"], winner="a/x", format="2p")
    store.save()

    reloaded = TrueSkillStore(path)
    assert reloaded.get_rating("a/x", format="2p").mu == store.get_rating("a/x", format="2p").mu
    assert reloaded.get_rating("a/x", format="2p").games_played == 1


def test_separate_ratings_per_format(tmp_path: Path):
    store = TrueSkillStore(tmp_path / "trueskill.json")

    store.update_match(agent_ids=["a/x", "b/y"], winner="a/x", format="2p")

    r2p = store.get_rating("a/x", format="2p")
    r4p = store.get_rating("a/x", format="4p")
    assert r2p.mu > TS_MU_0
    assert r4p.mu == TS_MU_0  # 4p fresh


def test_leaderboard_sorted_by_conservative(tmp_path: Path):
    store = TrueSkillStore(tmp_path / "trueskill.json")

    # a/x wygrywa vs b/y dużo razy → wyższy conservative
    for _ in range(5):
        store.update_match(agent_ids=["a/x", "b/y"], winner="a/x", format="2p")

    lb = store.leaderboard(format="2p")
    assert lb[0].agent_id == "a/x"
    assert lb[1].agent_id == "b/y"
    assert lb[0].rank == 1
    assert lb[1].rank == 2


def test_leaderboard_empty(tmp_path: Path):
    store = TrueSkillStore(tmp_path / "trueskill.json")
    assert store.leaderboard(format="2p") == []


def test_update_match_4p(tmp_path: Path):
    store = TrueSkillStore(tmp_path / "trueskill.json")

    store.update_match(
        agent_ids=["a/x", "b/y", "c/z", "d/w"], winner="c/z", format="4p"
    )

    assert store.get_rating("c/z", format="4p").mu > TS_MU_0
    assert store.get_rating("a/x", format="4p").mu < TS_MU_0
    assert store.get_rating("b/y", format="4p").mu < TS_MU_0
    assert store.get_rating("d/w", format="4p").mu < TS_MU_0
    # 2p format touched? nie
    assert store.get_rating("c/z", format="2p").mu == TS_MU_0


def test_save_writes_json(tmp_path: Path):
    path = tmp_path / "trueskill.json"
    store = TrueSkillStore(path)
    store.update_match(agent_ids=["a/x", "b/y"], winner="a/x", format="2p")
    store.save()

    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert "ratings" in data
    assert "a/x" in data["ratings"]
    assert "2p" in data["ratings"]["a/x"]


def test_snapshot_to(tmp_path: Path):
    store = TrueSkillStore(tmp_path / "trueskill.json")
    store.update_match(agent_ids=["a/x", "b/y"], winner="a/x", format="2p")
    store.save()

    snap = tmp_path / "snapshot.json"
    store.snapshot_to(snap)

    assert snap.exists()
    assert json.loads(snap.read_text()) == json.loads((tmp_path / "trueskill.json").read_text())
