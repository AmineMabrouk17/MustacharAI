"""Tests for the FastAPI health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from mustachar.api.app import app


@pytest.mark.asyncio
async def test_health_returns_200() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_returns_healthy_status() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/health")
    assert resp.json() == {"status": "healthy"}
