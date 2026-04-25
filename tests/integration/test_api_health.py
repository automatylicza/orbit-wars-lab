"""API: /api/health smoke test."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from orbit_wars_app.main import app


@pytest.mark.asyncio
async def test_api_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data
