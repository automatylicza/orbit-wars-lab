"""API: /api/runs endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from orbit_wars_app.main import app
from orbit_wars_app.schemas import TournamentConfig
from orbit_wars_app.tournament import Tournament


PROJECT_ROOT = Path(__file__).parent.parent.parent


def _run_one(tmp_path: Path) -> str:
    cfg = TournamentConfig(
        agents=["baselines/random", "baselines/random"],
        games_per_pair=1,
        mode="fast",
    )
    return Tournament(config=cfg, runs_root=tmp_path, zoo_root=PROJECT_ROOT / "agents").run()


@pytest.mark.asyncio
async def test_runs_empty_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/runs")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_runs_list_after_one_tournament(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    run_id = _run_one(tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/runs")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == run_id
    assert data[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_run_details(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    run_id = _run_one(tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/runs/{run_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == run_id
    assert "config" in data
    assert "results" in data
    assert len(data["results"]["matches"]) == 1


@pytest.mark.asyncio
async def test_run_details_404(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/runs/2099-01-01-999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_run_progress(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))
    run_id = _run_one(tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/runs/{run_id}/progress")
    assert r.status_code == 200
    data = r.json()
    assert data["matches_done"] == 1
    assert data["total_matches"] == 1
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_runs_exclude_quick_match_filters_flagged_runs(tmp_path: Path, monkeypatch):
    """Z ?exclude_quick_match=true zwracamy tylko runs z is_quick_match=False/brak."""
    monkeypatch.setenv("ORBIT_WARS_RUNS_DIR", str(tmp_path))

    # Normalny tournament (is_quick_match=False)
    cfg_normal = TournamentConfig(
        agents=["baselines/random", "baselines/random"],
        games_per_pair=1,
        mode="fast",
    )
    normal_id = Tournament(
        config=cfg_normal,
        runs_root=tmp_path,
        zoo_root=PROJECT_ROOT / "agents",
    ).run()

    # Quick match (is_quick_match=True)
    cfg_qm = TournamentConfig(
        agents=["baselines/random", "baselines/random"],
        games_per_pair=1,
        mode="fast",
        is_quick_match=True,
    )
    qm_id = Tournament(
        config=cfg_qm,
        runs_root=tmp_path,
        zoo_root=PROJECT_ROOT / "agents",
    ).run()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Default — oba widoczne
        r_all = await ac.get("/api/runs")
        assert r_all.status_code == 200
        ids_all = {r["id"] for r in r_all.json()}
        assert normal_id in ids_all
        assert qm_id in ids_all

        # Z filtrem — tylko normalny
        r_filtered = await ac.get("/api/runs?exclude_quick_match=true")
        assert r_filtered.status_code == 200
        ids_filtered = {r["id"] for r in r_filtered.json()}
        assert normal_id in ids_filtered
        assert qm_id not in ids_filtered
