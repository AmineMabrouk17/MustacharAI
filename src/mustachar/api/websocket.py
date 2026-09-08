"""WebSocket endpoint for real-time voice pipeline streaming."""

from __future__ import annotations

import json
import time

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mustachar.pipeline.orchestrator import run_pipeline_from_transcript
from mustachar.pipeline.stt import transcribe_pcm_segment
from mustachar.pipeline.tts import tts_stage
from mustachar.pipeline.vad import SpeechSegmenter

router = APIRouter()
logger = structlog.get_logger()


async def _send_json(websocket: WebSocket, payload: dict[str, object]) -> None:
    """Send a JSON message over the WebSocket."""
    await websocket.send_text(json.dumps(payload))


async def _transcribe_segment(
    segment: bytes, host: str, port: int
) -> tuple[str, float]:
    """Transcribe one VAD segment via Whisper and log the outcome.

    Returns ``(darja_text, latency_ms)``; ``darja_text`` is empty when Whisper
    returned nothing or transcription failed.
    """
    start = time.perf_counter()
    try:
        text = await transcribe_pcm_segment(segment)
    except Exception:
        logger.exception("ws.segment_stt_error", host=host, port=port)
        return "", 0.0
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "ws.segment_transcribed",
        host=host,
        port=port,
        transcript=text,
        bytes=len(segment),
        latency_ms=latency_ms,
    )
    return text, latency_ms


async def _send_transcript(
    websocket: WebSocket,
    *,
    partial: bool,
    darja_text: str,
    latency_ms: float,
) -> None:
    """Send a transcript message; ``partial`` marks an in-speech segment."""
    await _send_json(
        websocket,
        {
            "type": "transcript",
            "partial": partial,
            "darja_text": darja_text,
            "latency_ms": latency_ms,
        },
    )


@router.websocket("/api/v1/stream")
async def stream(websocket: WebSocket) -> None:
    """Accept a WebSocket connection for the full voice pipeline.

    Protocol:
      - Client streams raw 16 kHz / 16-bit / mono PCM chunks (binary frames).
      - Server runs a local VAD; each completed utterance is transcribed via
        Whisper and returned as ``transcript`` while the user still speaks.
      - Client sends ``{"type": "end"}`` on push-to-talk release.
      - Server flushes the final utterance, then runs the remaining pipeline
        (Reformulate → Retrieve → Generate → TTS) and sends:
        * ``transcript`` — the full Darja turn text
        * ``answer`` — the generated legal answer with citations
        * Binary audio parts — each TTS chunk is streamed as its own frame
          the moment it is synthesised, so audio starts before the whole
          answer is ready
    """
    await websocket.accept()
    client = websocket.client
    host = client.host if client else "unknown"
    port = client.port if client else 0
    logger.info("ws.connected", host=host, port=port)

    segmenter = SpeechSegmenter()
    transcripts: list[str] = []
    total_stt_latency_ms = 0.0

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                chunk = bytes(message["bytes"])
                for segment in segmenter.feed(chunk):
                    text, latency_ms = await _transcribe_segment(segment, host, port)
                    if text:
                        transcripts.append(text)
                        total_stt_latency_ms += latency_ms
                        await _send_transcript(
                            websocket,
                            partial=True,
                            darja_text=text,
                            latency_ms=latency_ms,
                        )
                continue

            raw_text = message.get("text")
            if raw_text is None:
                continue
            text_value = (
                raw_text
                if isinstance(raw_text, str)
                else raw_text.decode("utf-8")
                if isinstance(raw_text, bytes)
                else ""
            )
            try:
                payload = json.loads(text_value)
            except json.JSONDecodeError:
                continue

            if payload.get("type") != "end":
                continue

            for segment in segmenter.finish():
                text, latency_ms = await _transcribe_segment(segment, host, port)
                if text:
                    transcripts.append(text)
                    total_stt_latency_ms += latency_ms
                    await _send_transcript(
                        websocket,
                        partial=True,
                        darja_text=text,
                        latency_ms=latency_ms,
                    )

            turn_text = " ".join(part.strip() for part in transcripts if part.strip())
            if not turn_text:
                await _send_json(websocket, {"type": "status", "stage": "idle"})
                transcripts = []
                total_stt_latency_ms = 0.0
                continue

            await _send_transcript(
                websocket,
                partial=False,
                darja_text=turn_text,
                latency_ms=total_stt_latency_ms,
            )

            # --- Pipeline stages: Reformulate → Retrieve → Generate ---
            await _send_json(
                websocket,
                {"type": "status", "stage": "processing"},
            )

            try:
                result = await run_pipeline_from_transcript(turn_text)
            except Exception:
                logger.exception("ws.pipeline_error", host=host, port=port)
                await _send_json(
                    websocket,
                    {
                        "type": "answer",
                        "text": "Une erreur est survenue pendant le traitement. "
                        "Veuillez réessayer.",
                        "citations": [],
                        "fallback": True,
                        "latency_ms": 0,
                        "stage_latencies_ms": {},
                    },
                )
                transcripts = []
                total_stt_latency_ms = 0.0
                continue

            await _send_json(
                websocket,
                {
                    "type": "answer",
                    "text": result.answer,
                    "citations": result.citations,
                    "fallback": result.fallback,
                    "latency_ms": result.stage_latencies_ms.get("retrieve_generate", 0),
                    "stage_latencies_ms": result.stage_latencies_ms,
                },
            )

            # --- TTS stage ---
            await _send_json(
                websocket,
                {"type": "status", "stage": "speaking"},
            )

            try:
                part_count = 0
                async for chunk in tts_stage(result.answer):
                    await websocket.send_bytes(chunk)
                    part_count += 1
                logger.info(
                    "ws.tts_streamed",
                    host=host,
                    port=port,
                    parts=part_count,
                    answer_length=len(result.answer),
                )
            except Exception:
                logger.exception("ws.tts_error", host=host, port=port)

            await _send_json(
                websocket,
                {"type": "status", "stage": "idle"},
            )

            transcripts = []
            total_stt_latency_ms = 0.0

    except WebSocketDisconnect:
        logger.info("ws.disconnected", host=host, port=port)
