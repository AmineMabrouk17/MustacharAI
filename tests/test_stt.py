"""Tests for the STT pipeline stage."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mustachar.pipeline.stt import speech_to_text


@pytest.mark.asyncio
@patch("mustachar.pipeline.stt.transcribe", return_value="أهلا")
async def test_speech_to_text_returns_transcript(mock_transcribe: AsyncMock) -> None:
    result = await speech_to_text(b"fake-audio", "clip.webm")

    assert result == "أهلا"
    mock_transcribe.assert_awaited_once_with(audio=("clip.webm", b"fake-audio"))


@pytest.mark.asyncio
@patch("mustachar.pipeline.stt.transcribe", return_value="تمام")
async def test_speech_to_text_logs_latency(mock_transcribe: AsyncMock) -> None:
    await speech_to_text(b"audio-bytes", "test.ogg")

    mock_transcribe.assert_awaited_once()
