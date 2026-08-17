"""Text-to-Speech pipeline stage."""

import time
from collections.abc import AsyncIterator

import structlog

from mustachar.infra.edge_tts_client import DEFAULT_VOICE, synthesize

logger = structlog.get_logger()


async def tts_stage(text: str, voice: str = DEFAULT_VOICE) -> AsyncIterator[bytes]:
    """Synthesize *text* to speech and return audio bytes.

    Logs the wall-clock latency for the full synthesis.
    """
    start = time.perf_counter()
    async for chunk in synthesize(text, voice=voice):
        yield chunk
    elapsed_ms = (time.perf_counter() - start) * 1000
    await logger.ainfo(
        "tts_completed", text_length=len(text), latency_ms=round(elapsed_ms, 2)
    )


async def tts_full(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """Collect all audio chunks into a single ``bytes`` object."""
    parts: list[bytes] = []
    async for chunk in tts_stage(text, voice=voice):
        parts.append(chunk)
    return b"".join(parts)
