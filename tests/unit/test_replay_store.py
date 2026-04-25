"""Tests for orbit_wars_app.replay_store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orbit_wars_app.replay_store import (
    agent_id_to_safe,
    make_match_filename,
    save_replay,
    load_replay,
)


FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_agent_id_to_safe_replaces_slash():
    assert agent_id_to_safe("mine/v1-combat-aware") == "mine_v1-combat-aware"
    assert agent_id_to_safe("baselines/random") == "baselines_random"
    assert agent_id_to_safe("external/tamrazov-1224") == "external_tamrazov-1224"


def test_make_match_filename_2p():
    fn = make_match_filename(1, ["mine/v1", "external/tamrazov-1224"])
    assert fn == "001-mine_v1__vs__external_tamrazov-1224.json"


def test_make_match_filename_zero_pads_to_3_digits():
    fn = make_match_filename(42, ["a/x", "b/y"])
    assert fn == "042-a_x__vs__b_y.json"


def test_make_match_filename_4p():
    fn = make_match_filename(7, ["a/x", "b/y", "c/z", "d/w"])
    assert fn == "007-a_x__vs__b_y__vs__c_z__vs__d_w.json"


def test_save_replay_writes_json(tmp_path: Path):
    replays_dir = tmp_path / "replays"
    replays_dir.mkdir()

    sample = json.loads((FIXTURES / "minimal_replay.json").read_text())

    path = save_replay(replays_dir, match_id=1, agent_ids=["a/x", "b/y"], replay=sample)

    assert path.exists()
    assert path.name == "001-a_x__vs__b_y.json"

    # Payload zgodny
    loaded = json.loads(path.read_text())
    assert loaded == sample


def test_load_replay_roundtrip(tmp_path: Path):
    replays_dir = tmp_path / "replays"
    replays_dir.mkdir()
    sample = json.loads((FIXTURES / "minimal_replay.json").read_text())

    path = save_replay(replays_dir, match_id=1, agent_ids=["a/x", "b/y"], replay=sample)
    loaded = load_replay(path)

    assert loaded == sample


def test_load_replay_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_replay(tmp_path / "nonexistent.json")


def test_save_replay_overwrites(tmp_path: Path):
    replays_dir = tmp_path / "replays"
    replays_dir.mkdir()
    sample = json.loads((FIXTURES / "minimal_replay.json").read_text())

    path1 = save_replay(replays_dir, match_id=1, agent_ids=["a/x", "b/y"], replay=sample)
    path2 = save_replay(replays_dir, match_id=1, agent_ids=["a/x", "b/y"], replay={"mutated": True})

    assert path1 == path2
    assert json.loads(path2.read_text()) == {"mutated": True}
