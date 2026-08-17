"""Async wrapper around the Groq SDK for Whisper STT."""

from __future__ import annotations

from typing import TYPE_CHECKING

import groq

from mustachar.core.settings import settings

if TYPE_CHECKING:
    from groq._types import FileTypes


_client: groq.AsyncGroq | None = None


def _get_client() -> groq.AsyncGroq:
    global _client
    if _client is None:
        _client = groq.AsyncGroq(api_key=settings.groq_api_key)
    return _client


async def transcribe(
    audio: FileTypes,
    *,
    model: str = "whisper-large-v3",
    language: str = "ar",
) -> str:
    """Send raw audio bytes to Groq Whisper and return the transcript text."""
    client = _get_client()
    response = await client.audio.transcriptions.create(
        model=model,
        file=audio,
        language=language,
    )
    return response.text
