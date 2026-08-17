"""Edge-TTS client for speech synthesis."""

from collections.abc import AsyncIterator

import edge_tts
import structlog

logger = structlog.get_logger()

DEFAULT_VOICE = "ar-TN-HediNeural"


async def synthesize(text: str, voice: str = DEFAULT_VOICE) -> AsyncIterator[bytes]:
    """Stream audio bytes from Edge-TTS for the given *text*.

    Yields chunks of MP3 audio as they become available.
    """
    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]
