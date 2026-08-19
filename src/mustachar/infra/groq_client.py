"""Async wrapper around the Groq SDK for Whisper STT and LLM chat."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

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


async def chat(
    messages: list[dict[str, str]],
    *,
    model: str = "",
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """Send a chat completion request and return the response text."""
    if not model:
        model = settings.groq_chat_model
    client = _get_client()
    response = await client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content: Any = response.choices[0].message.content
    return content if isinstance(content, str) else ""


async def chat_json(
    messages: list[dict[str, str]],
    *,
    model: str = "",
    temperature: float = 0.3,
    max_tokens: int = 256,
) -> str:
    """Send a chat completion request and extract a JSON object from the response.

    Returns the raw JSON string.  The model is asked via prompt to return JSON;
    ``response_format`` is not used because not all Groq models support it.
    """
    if not model:
        model = settings.groq_chat_model
    client = _get_client()
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content: Any = response.choices[0].message.content
    text = content if isinstance(content, str) else ""

    # Try to extract a JSON object from the response (handles markdown fences)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]

    raise json.JSONDecodeError("No JSON object found in response", text, 0)
