"""Tests dla CLI tags filter w tournament.py."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest
import yaml

from orbit_wars_app.schemas import AgentInfo
from orbit_wars_app.tournament import _filter_agents_by_tags


def _ainfo(aid: str, bucket: str, tags: list[str], disabled: bool = False) -> AgentInfo:
    return AgentInfo(
        id=aid,
        name=aid.split("/")[-1],
        bucket=bucket,  # type: ignore[arg-type]
        tags=tags,
        disabled=disabled,
        has_yaml=True,
        path=f"agents/{aid}",
    )


def test_filter_by_single_tag_or():
    """--tag benchmark → wszystkie z tagiem 'benchmark'."""
    agents = [
        _ainfo("external/a", "external", ["benchmark", "rule-based"]),
        _ainfo("external/b", "external", ["rule-based"]),
        _ainfo("baselines/c", "baselines", ["benchmark"]),
    ]
    result = _filter_agents_by_tags(agents, include=["benchmark"], exclude=[])
    assert [a.id for a in result] == ["external/a", "baselines/c"]


def test_filter_by_multiple_include_tags_is_or():
    """--tag a --tag b → dowolny z (a, b)."""
    agents = [
        _ainfo("external/a", "external", ["benchmark"]),
        _ainfo("external/b", "external", ["quick"]),
        _ainfo("external/c", "external", ["slow"]),
    ]
    result = _filter_agents_by_tags(agents, include=["benchmark", "quick"], exclude=[])
    assert [a.id for a in result] == ["external/a", "external/b"]


def test_filter_exclude_tag_is_and():
    """--tag rule-based --exclude-tag slow → rule-based AND NOT slow."""
    agents = [
        _ainfo("external/a", "external", ["rule-based"]),
        _ainfo("external/b", "external", ["rule-based", "slow"]),
        _ainfo("external/c", "external", ["rule-based", "slow", "broken"]),
    ]
    result = _filter_agents_by_tags(agents, include=["rule-based"], exclude=["slow"])
    assert [a.id for a in result] == ["external/a"]


def test_filter_no_include_means_all():
    """Brak --tag → wszystkie przechodzą (potem exclude może trimować)."""
    agents = [
        _ainfo("external/a", "external", ["rule-based"]),
        _ainfo("external/b", "external", ["broken"]),
    ]
    result = _filter_agents_by_tags(agents, include=[], exclude=["broken"])
    assert [a.id for a in result] == ["external/a"]


def test_filter_disabled_agents_always_excluded():
    """disabled: true → zawsze pomijany, niezależnie od tagów."""
    agents = [
        _ainfo("external/a", "external", ["benchmark"]),
        _ainfo("external/b", "external", ["benchmark"], disabled=True),
    ]
    result = _filter_agents_by_tags(agents, include=["benchmark"], exclude=[])
    assert [a.id for a in result] == ["external/a"]
