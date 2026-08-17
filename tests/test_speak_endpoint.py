"""Tests for the /api/v1/speak endpoint."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from mustachar.api.app import app


async def _fake_stream(items: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    for item in items:
        yield item


def _mock_communicate(chunks: list[dict[str, Any]]) -> MagicMock:
    mock = MagicMock()
    mock.stream.return_value = _fake_stream(chunks)
    return mock


@pytest.mark.asyncio
async def test_speak_returns_audio_mpeg() -> None:
    fake_chunks: list[dict[str, Any]] = [
        {"type": "audio", "data": b"\xff\xfb\x90\x00"},
        {"type": "audio", "data": b"\xff\xfb\x90\x01"},
    ]

    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate",
        return_value=_mock_communicate(fake_chunks),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.post("/api/v1/speak", json={"text": "marhaba"})

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == b"\xff\xfb\x90\x00\xff\xfb\x90\x01"


@pytest.mark.asyncio
async def test_speak_rejects_empty_text() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post("/api/v1/speak", json={"text": ""})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_speak_uses_custom_voice() -> None:
    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate",
        return_value=_mock_communicate([{"type": "audio", "data": b"data"}]),
    ) as mock_cls:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            await client.post(
                "/api/v1/speak",
                json={"text": "test", "voice": "en-US-AriaNeural"},
            )

    mock_cls.assert_called_once_with("test", "en-US-AriaNeural")
