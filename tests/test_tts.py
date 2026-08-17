"""Tests for the TTS pipeline stage."""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest


async def _fake_stream(items: list[dict]) -> AsyncIterator[dict]:  # type: ignore[misc]
    for item in items:
        yield item


def _mock_communicate(chunks: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.stream.return_value = _fake_stream(chunks)
    return mock


@pytest.mark.asyncio
async def test_tts_stage_yields_chunks() -> None:
    fake_chunks = [
        {"type": "audio", "data": b"chunk1"},
        {"type": "audio", "data": b"chunk2"},
    ]

    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate",
        return_value=_mock_communicate(fake_chunks),
    ):
        from mustachar.pipeline.tts import tts_stage

        result: list[bytes] = []
        async for chunk in tts_stage("ahlan"):
            result.append(chunk)

    assert result == [b"chunk1", b"chunk2"]


@pytest.mark.asyncio
async def test_tts_full_collects_all_bytes() -> None:
    fake_chunks = [
        {"type": "audio", "data": b"aa"},
        {"type": "audio", "data": b"bb"},
        {"type": "audio", "data": b"cc"},
    ]

    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate",
        return_value=_mock_communicate(fake_chunks),
    ):
        from mustachar.pipeline.tts import tts_full

        audio = await tts_full("test full")

    assert audio == b"aabbcc"


@pytest.mark.asyncio
async def test_tts_full_returns_empty_bytes_when_no_audio() -> None:
    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate",
        return_value=_mock_communicate([{"type": "WordBoundary", "data": {}}]),
    ):
        from mustachar.pipeline.tts import tts_full

        audio = await tts_full("silent")

    assert audio == b""
