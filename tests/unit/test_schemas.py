"""Tests dla Pydantic schemas w orbit_wars_app."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from orbit_wars_app.schemas import (
    AgentInfo,
    AgentLogsResponse,
    KaggleSubmission,
    RunSummary,
    TournamentConfig,
)


def test_agent_info_accepts_new_external_fields():
    """Po Task 1 AgentInfo ma: kernel_slug, kernel_version, license, author_claimed_lb_score."""
    info = AgentInfo(
        id="external/tamrazov-starwars",
        name="Tamrazov Starwars",
        bucket="external",
        kernel_slug="romantamrazov/orbit-star-wars-lb-max-1224",
        kernel_version=6,
        license="Apache 2.0",
        author_claimed_lb_score=1224.0,
        has_yaml=True,
        path="agents/external/tamrazov-starwars",
    )
    assert info.kernel_slug == "romantamrazov/orbit-star-wars-lb-max-1224"
    assert info.kernel_version == 6
    assert info.license == "Apache 2.0"
    assert info.author_claimed_lb_score == 1224.0


def test_agent_info_new_fields_optional():
    """Baseline agent nie ma kernel_slug — pola są optional."""
    info = AgentInfo(
        id="baselines/random",
        name="Random",
        bucket="baselines",
        has_yaml=True,
        path="agents/baselines/random",
    )
    assert info.kernel_slug is None
    assert info.kernel_version is None
    assert info.license is None
    assert info.author_claimed_lb_score is None


def test_agent_info_preserves_deprecated_source_url_and_version():
    """Backward compat — source_url i version zostają przyjmowane (deprecated, nie usunięte)."""
    info = AgentInfo(
        id="external/legacy",
        name="Legacy",
        bucket="external",
        source_url="https://www.kaggle.com/old-style-url",
        version="3",
        has_yaml=True,
        path="agents/external/legacy",
    )
    assert info.source_url == "https://www.kaggle.com/old-style-url"
    assert info.version == "3"


# ===== Quick Match UI: is_quick_match field tests =====
def test_tournament_config_has_is_quick_match_default_false():
    cfg = TournamentConfig(agents=["baselines/random", "baselines/starter"])
    assert cfg.is_quick_match is False


def test_tournament_config_accepts_is_quick_match_true():
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/starter"],
        is_quick_match=True,
    )
    assert cfg.is_quick_match is True


def test_run_summary_has_is_quick_match_default_false():
    rs = RunSummary(id="2026-04-21-001", started_at="2026-04-21T12:00:00Z")
    assert rs.is_quick_match is False


def test_run_summary_accepts_is_quick_match_true():
    rs = RunSummary(
        id="2026-04-21-001",
        started_at="2026-04-21T12:00:00Z",
        is_quick_match=True,
    )
    assert rs.is_quick_match is True


def test_kaggle_submission_all_fields():
    s = KaggleSubmission(
        submission_id=51799179,
        description="v1-my-bot",
        date="2026-04-20T12:34:56Z",
        status="COMPLETE",
        mu=742.3,
        sigma=26.1,
        rank=43,
        games_played=187,
    )
    d = s.model_dump()
    assert d["submission_id"] == 51799179
    assert d["mu"] == 742.3


def test_kaggle_submission_minimal_optional_fields():
    s = KaggleSubmission(
        submission_id=1,
        description="",
        date="2026-04-20T00:00:00Z",
        status="PENDING",
    )
    assert s.mu is None
    assert s.sigma is None
    assert s.rank is None
    assert s.games_played is None


def test_agent_logs_response():
    r = AgentLogsResponse(
        submission_id=123, episode_id=456, agent_idx=0, text="line1\nline2"
    )
    assert r.model_dump()["text"] == "line1\nline2"
