"""API: /api/replays/{run_id}/{match_id}."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from orbit_wars_app.main import app
from orbit_wars_app.schemas import TournamentConfig
from orbit_wars_app.tournament import Tournament


PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.asyncio
async def test_get_replay_returns_native_json(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/random"],
        games_per_pair=1,
        mode="fast",
    )
    run_id = Tournament(
        config=cfg, runs_root=tmp_path, zoo_root=PROJECT_ROOT / "agents",
    ).run()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/replays/{run_id}/001")
    assert r.status_code == 200
    replay = r.json()
    # Native env.toJSON() shape
    assert "steps" in replay
    assert isinstance(replay["steps"], list)
    assert len(replay["steps"]) > 0


@pytest.mark.asyncio
async def test_get_replay_404(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/replays/2099-01-01-999/042")
    assert r.status_code == 404
