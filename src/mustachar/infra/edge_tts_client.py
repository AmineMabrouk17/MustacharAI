"""Edge-TTS client for speech synthesis."""

from collections.abc import AsyncIterator

import edge_tts
import structlog

from mustachar.core.settings import settings

logger = structlog.get_logger()

DEFAULT_VOICE = settings.tts_voice

# Known-good French neural voices tried when even the default is retired.
BACKUP_VOICES = ("fr-FR-HenriNeural", "fr-FR-DeniseNeural", "fr-FR-EloiseNeural")

_available_voices: frozenset[str] | None = None


async def _available_voice_names() -> frozenset[str]:
    """Return the set of voices Edge-TTS currently serves (cached)."""
    global _available_voices
    if _available_voices is None:
        voices = await edge_tts.list_voices()
        _available_voices = frozenset(v["ShortName"] for v in voices)
    return _available_voices


async def _resolve_voice(voice: str) -> str:
    """Return a voice Edge-TTS currently serves, preferring *voice*.

    Voices are retired without warning; synthesising with a voice Edge no
    longer serves yields silent audio. The guard runs once per process: it
    prefers the requested voice, then the configured default, then the first
    available French backup. If the availability list itself cannot be fetched,
    the requested voice is used as-is so the guard never blocks synthesis.
    """
    try:
        available = await _available_voice_names()
    except Exception:
        logger.warning("tts.voice_list_unavailable", requested=voice, exc_info=True)
        return voice
    if voice in available:
        return voice
    if DEFAULT_VOICE in available:
        logger.warning("tts.voice_unavailable", requested=voice, fallback=DEFAULT_VOICE)
        return DEFAULT_VOICE
    backup = next((v for v in BACKUP_VOICES if v in available), voice)
    logger.warning("tts.voice_fallback", requested=voice, fallback=backup)
    return backup


async def synthesize(text: str, voice: str = DEFAULT_VOICE) -> AsyncIterator[bytes]:
    """Stream audio bytes from Edge-TTS for the given *text*.

    Yields chunks of MP3 audio as they become available.
    """
    resolved = await _resolve_voice(voice)
    communicate = edge_tts.Communicate(text, resolved)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]
