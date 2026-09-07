"""Local voice-activity detection for streaming speech segmentation.

The streamed audio arrives as raw 16 kHz / 16-bit / mono PCM chunks from the
frontend. The :class:`SpeechSegmenter` splits that stream into utterances by
running an energy-based VAD over 30 ms frames and emitting a completed
utterance once the trailing silence exceeds ``silence_ms`` (or once an
utterance grows beyond ``max_utterance_ms``).
"""

from __future__ import annotations

import array
import math

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_FRAME_MS = 30
DEFAULT_SPEECH_RMS = 400.0
DEFAULT_THRESHOLD_RATIO = 2.0
DEFAULT_SILENCE_MS = 500
DEFAULT_MIN_SPEECH_MS = 120
DEFAULT_MAX_UTTERANCE_MS = 8000


def _rms(frame: bytes) -> float:
    """Return the root-mean-square amplitude of an int16 little-endian frame."""
    samples = array.array("h", frame)
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


class SpeechSegmenter:
    """Split a raw PCM stream into end-detected utterance segments."""

    def __init__(
        self,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        frame_ms: int = DEFAULT_FRAME_MS,
        speech_rms: float = DEFAULT_SPEECH_RMS,
        threshold_ratio: float = DEFAULT_THRESHOLD_RATIO,
        silence_ms: int = DEFAULT_SILENCE_MS,
        min_speech_ms: int = DEFAULT_MIN_SPEECH_MS,
        max_utterance_ms: int = DEFAULT_MAX_UTTERANCE_MS,
    ) -> None:
        self._frame_len = max(1, int(sample_rate * frame_ms / 1000))
        self._frame_bytes = self._frame_len * 2
        self._silence_frames = max(1, int(silence_ms / frame_ms))
        self._min_speech_frames = max(1, int(min_speech_ms / frame_ms))
        self._max_speech_frames = max(1, int(max_utterance_ms / frame_ms))
        self._min_speech_rms = speech_rms
        self._threshold_ratio = threshold_ratio
        self._noise_floor = speech_rms

        self._buffer = bytearray()
        self._candidate = bytearray()
        self._speech_frames = 0
        self._silence_run = 0
        self._speech_active = False

    def feed(self, chunk: bytes) -> list[bytes]:
        """Consume a PCM chunk and return any completed utterances."""
        self._buffer.extend(chunk)
        completed: list[bytes] = []
        while len(self._buffer) >= self._frame_bytes:
            frame = bytes(self._buffer[: self._frame_bytes])
            del self._buffer[: self._frame_bytes]
            utterance = self._step(frame)
            if utterance is not None:
                completed.append(utterance)
        return completed

    def finish(self) -> list[bytes]:
        """Force-emit the pending utterance (end of turn or disconnect)."""
        if self._speech_frames >= self._min_speech_frames:
            utterance = bytes(self._candidate)
            self._reset()
            return [utterance]
        self._reset()
        return []

    def _step(self, frame: bytes) -> bytes | None:
        rms = _rms(frame)
        if rms >= self._threshold():
            self._speech_active = True
            self._speech_frames += 1
            self._silence_run = 0
            self._candidate.extend(frame)
            if self._speech_frames >= self._max_speech_frames:
                utterance = bytes(self._candidate)
                self._reset()
                return utterance
        elif self._speech_active:
            self._silence_run += 1
            self._candidate.extend(frame)
            if self._silence_run >= self._silence_frames:
                utterance = bytes(self._candidate)
                self._reset()
                return utterance
        else:
            self._noise_floor = 0.95 * self._noise_floor + 0.05 * rms
        return None

    def _threshold(self) -> float:
        return max(self._min_speech_rms, self._noise_floor * self._threshold_ratio)

    def _reset(self) -> None:
        self._candidate = bytearray()
        self._speech_frames = 0
        self._silence_run = 0
        self._speech_active = False
