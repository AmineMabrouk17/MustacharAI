"""Tests for the Edge-TTS client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _fake_stream(items: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    for item in items:
        yield item


def _mock_communicate(chunks: list[dict[str, Any]]) -> MagicMock:
    mock = MagicMock()
    mock.stream.return_value = _fake_stream(chunks)
    return mock


@pytest.mark.asyncio
async def test_synthesize_yields_audio_chunks() -> None:
    fake_chunks: list[dict[str, Any]] = [
        {"type": "audio", "data": b"\xff\xfb\x90\x00"},
        {"type": "audio", "data": b"\xff\xfb\x90\x01"},
        {"type": "WordBoundary", "data": {}},
        {"type": "audio", "data": b"\xff\xfb\x90\x02"},
    ]

    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate",
        return_value=_mock_communicate(fake_chunks),
    ):
        from mustachar.infra.edge_tts_client import synthesize

        result: list[bytes] = []
        async for chunk in synthesize("marhaba"):
            result.append(chunk)

    assert result == [b"\xff\xfb\x90\x00", b"\xff\xfb\x90\x01", b"\xff\xfb\x90\x02"]


@pytest.mark.asyncio
async def test_synthesize_returns_empty_for_no_audio() -> None:
    fake_chunks: list[dict[str, Any]] = [
        {"type": "WordBoundary", "data": {}},
        {"type": "SentenceBoundary", "data": {}},
    ]

    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate",
        return_value=_mock_communicate(fake_chunks),
    ):
        from mustachar.infra.edge_tts_client import synthesize

        collected = [chunk async for chunk in synthesize("empty")]

    assert collected == []


@pytest.mark.asyncio
async def test_synthesize_uses_default_voice() -> None:
    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate",
        return_value=_mock_communicate([]),
    ) as mock_cls:
        from mustachar.infra.edge_tts_client import synthesize

        _ = [chunk async for chunk in synthesize("test")]

    mock_cls.assert_called_once_with("test", "ar-TN-HediNeural")
