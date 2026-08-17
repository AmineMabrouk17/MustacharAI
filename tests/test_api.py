"""Tests for the FastAPI health endpoint."""

from unittest.mock import patch

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


@pytest.mark.asyncio
@patch("mustachar.api.app.speech_to_text", return_value="مرحبا")
async def test_ask_returns_transcript(mock_stt: object) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            "/api/v1/ask",
            files={"audio": ("clip.webm", b"fake-audio", "audio/webm")},
        )
    assert resp.status_code == 200
    assert resp.json() == {"transcript": "مرحبا"}
