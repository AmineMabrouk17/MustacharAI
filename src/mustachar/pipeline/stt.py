"""Speech-to-text pipeline stage."""

from __future__ import annotations

import time

import structlog

from mustachar.infra.groq_client import transcribe

logger = structlog.get_logger()


async def speech_to_text(audio_bytes: bytes, filename: str) -> str:
    """Accept raw browser audio and return a Darja transcript.

    Zero-transcoding: the raw webm/opus bytes are passed directly to Groq.
    """
    start = time.perf_counter()
    transcript = await transcribe(
        audio=(filename, audio_bytes),
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info("stt_completed", latency_ms=round(elapsed_ms, 1))
    return transcript
