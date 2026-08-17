"""Tests for the Groq client wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mustachar.infra.groq_client import transcribe


@pytest.mark.asyncio
@patch("mustachar.infra.groq_client._get_client")
async def test_transcribe_returns_text(mock_get: AsyncMock) -> None:
    mock_response = AsyncMock()
    mock_response.text = "مرحبا بالعالم"
    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create.return_value = mock_response
    mock_get.return_value = mock_client

    result = await transcribe(audio=("test.webm", b"fake-audio-data"))

    assert result == "مرحبا بالعالم"
    mock_client.audio.transcriptions.create.assert_awaited_once()
