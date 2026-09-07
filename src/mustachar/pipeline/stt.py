"""Speech-to-text pipeline stage."""

from __future__ import annotations

import struct
import time

import structlog

from mustachar.infra.groq_client import transcribe

logger = structlog.get_logger()


def pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap raw 16-bit mono PCM samples in a WAV container.

    Whisper consumes the same samples the streaming VAD saw — this adds only
    the 44-byte header, never re-encodes the audio.
    """
    num_channels = 1
    bits_per_sample = 16
    block_align = num_channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,  # WAVE_FORMAT_PCM
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        len(pcm),
    )
    return header + pcm


async def speech_to_text(audio_bytes: bytes, filename: str) -> str:
    """Accept raw browser audio and return a Darja transcript.

    Zero-transcoding: the raw webm/opus bytes are passed directly to Groq.
    """
    start = time.perf_counter()
    transcript = await transcribe(
        audio=(filename, audio_bytes),
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "stt_completed", latency_ms=round(elapsed_ms, 1), bytes=len(audio_bytes)
    )
    return transcript


async def transcribe_pcm_segment(pcm: bytes, sample_rate: int = 16000) -> str:
    """Transcribe one VAD-detected PCM segment via Groq Whisper."""
    start = time.perf_counter()
    wav = pcm_to_wav(pcm, sample_rate)
    transcript = await transcribe(
        audio=(f"segment-{sample_rate}.wav", wav),
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "stt_segment_completed",
        latency_ms=round(elapsed_ms, 1),
        bytes=len(pcm),
    )
    return transcript
