"""API: /api/agents endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from orbit_wars_app.main import app


@pytest.mark.asyncio
async def test_api_agents_lists_baselines():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/agents")

    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    ids = {a["id"] for a in data}
    assert "baselines/random" in ids
    assert "baselines/nearest-sniper" in ids
    assert "baselines/starter" in ids


@pytest.mark.asyncio
async def test_api_agents_detail_returns_metadata():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/agents/baselines/nearest-sniper")

    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "baselines/nearest-sniper"
    assert data["name"] == "Nearest Planet Sniper"
    assert data["bucket"] == "baselines"
    assert "rule-based" in data["tags"]


@pytest.mark.asyncio
async def test_api_agents_detail_404_for_missing():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/agents/nonexistent/agent")
    assert r.status_code == 404
