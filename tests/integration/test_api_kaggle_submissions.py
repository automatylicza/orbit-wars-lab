"""API: /api/kaggle-submissions endpoints."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from orbit_wars_app import kaggle_submissions as ks
from orbit_wars_app.kaggle_submissions import KaggleCliError
from orbit_wars_app.main import app


@pytest.mark.asyncio
async def test_list_submissions_happy(monkeypatch):
    ks._submissions_cache.clear()
    from orbit_wars_app.schemas import KaggleSubmission

    fake = [
        KaggleSubmission(
            submission_id=123,
            description="v1",
            date="2026-04-20T00:00:00",
            status="COMPLETE",
            mu=742.0,
        )
    ]
    monkeypatch.setattr(
        ks, "list_my_submissions", lambda competition="orbit-wars": fake
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/kaggle-submissions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["description"] == "v1"
    assert data[0]["mu"] == 742.0


@pytest.mark.asyncio
async def test_list_submissions_auth_fail_returns_401(monkeypatch):
    ks._submissions_cache.clear()

    def boom(competition="orbit-wars"):
        raise KaggleCliError(401, "Kaggle token expired")

    monkeypatch.setattr(ks, "list_my_submissions", boom)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/kaggle-submissions")
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_submissions_cli_not_found_returns_500(monkeypatch):
    ks._submissions_cache.clear()

    def boom(competition="orbit-wars"):
        raise KaggleCliError(500, "Kaggle CLI not found at /bad/path")

    monkeypatch.setattr(ks, "list_my_submissions", boom)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/kaggle-submissions")
    assert r.status_code == 500
    assert "not found" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_logs_happy_with_inferred_idx(monkeypatch):
    monkeypatch.setattr(
        ks, "infer_my_agent_idx",
        lambda sub, ep, replays_root: 1,
    )
    monkeypatch.setattr(
        ks, "fetch_agent_logs",
        lambda episode_id, agent_idx, cwd=None: "turn 23: WARN\n",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/kaggle-submissions/51799179/episodes/70123456/logs")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_idx"] == 1
    assert data["text"] == "turn 23: WARN\n"


@pytest.mark.asyncio
async def test_logs_fallback_to_idx_0_when_inference_fails(monkeypatch):
    monkeypatch.setattr(
        ks, "infer_my_agent_idx",
        lambda sub, ep, replays_root: None,
    )
    calls: list[int] = []

    def fake_fetch(episode_id, agent_idx, cwd=None):
        calls.append(agent_idx)
        if agent_idx == 0:
            return "my own logs\n"
        raise KaggleCliError(403, "Forbidden")

    monkeypatch.setattr(ks, "fetch_agent_logs", fake_fetch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/kaggle-submissions/51799179/episodes/70123456/logs")
    assert r.status_code == 200
    assert r.json()["agent_idx"] == 0
    assert calls == [0]


@pytest.mark.asyncio
async def test_logs_fallback_to_idx_1_when_idx_0_is_opponent(monkeypatch):
    monkeypatch.setattr(
        ks, "infer_my_agent_idx",
        lambda sub, ep, replays_root: None,
    )
    calls: list[int] = []

    def fake_fetch(episode_id, agent_idx, cwd=None):
        calls.append(agent_idx)
        if agent_idx == 1:
            return "second player logs\n"
        raise KaggleCliError(403, "Forbidden")

    monkeypatch.setattr(ks, "fetch_agent_logs", fake_fetch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/kaggle-submissions/51799179/episodes/70123456/logs")
    assert r.status_code == 200
    assert r.json()["agent_idx"] == 1
    assert calls == [0, 1]


@pytest.mark.asyncio
async def test_logs_fallback_both_403_returns_404(monkeypatch):
    monkeypatch.setattr(
        ks, "infer_my_agent_idx",
        lambda sub, ep, replays_root: None,
    )

    def always_403(episode_id, agent_idx, cwd=None):
        raise KaggleCliError(403, "Forbidden")

    monkeypatch.setattr(ks, "fetch_agent_logs", always_403)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/kaggle-submissions/51799179/episodes/70123456/logs")
    assert r.status_code == 404
    assert "agent index" in r.json()["detail"].lower()
