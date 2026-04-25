"""API: /api/ratings leaderboard."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from orbit_wars_app.main import app
from orbit_wars_app.schemas import TournamentConfig
from orbit_wars_app.tournament import Tournament


PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.asyncio
async def test_ratings_empty_before_any_tournament(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/ratings?format=2p")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_ratings_after_tournament(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/nearest-sniper"],
        games_per_pair=2,
        mode="fast",
    )
    Tournament(config=cfg, runs_root=tmp_path, zoo_root=PROJECT_ROOT / "agents").run()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/ratings?format=2p")
    assert r.status_code == 200
    ratings = r.json()
    ids = {x["agent_id"] for x in ratings}
    assert ids == {"baselines/random", "baselines/nearest-sniper"}
    for rating in ratings:
        assert "mu" in rating
        assert "sigma" in rating
        assert "conservative" in rating
        assert "games_played" in rating
        assert "rank" in rating
    # Ranked 1..N
    ranks = sorted(r["rank"] for r in ratings)
    assert ranks == [1, 2]


@pytest.mark.asyncio
async def test_ratings_invalid_format_422(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/ratings?format=8p")
    assert r.status_code == 422
