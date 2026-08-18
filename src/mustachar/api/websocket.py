"""WebSocket endpoint for real-time voice pipeline streaming."""

from __future__ import annotations

import json
import time

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mustachar.pipeline.generator import generate
from mustachar.pipeline.stt import speech_to_text
from mustachar.pipeline.tts import tts_stage

router = APIRouter()
logger = structlog.get_logger()


async def _send_json(websocket: WebSocket, payload: dict[str, object]) -> None:
    """Send a JSON message over the WebSocket."""
    await websocket.send_text(json.dumps(payload))


@router.websocket("/api/v1/stream")
async def stream(websocket: WebSocket) -> None:
    """Accept a WebSocket connection for the full voice pipeline.

    Protocol:
      - Client sends binary audio frames (webm/opus).
      - Server responds with ``status`` messages at each pipeline stage.
      - Server runs STT → RAG retrieval → generation → TTS and sends:
        * ``transcript`` — the recognised Darja text
        * ``answer`` — the generated legal answer with citations
        * Binary audio frames for the TTS output
    """
    await websocket.accept()
    client = websocket.client
    host = client.host if client else "unknown"
    port = client.port if client else 0
    logger.info("ws.connected", host=host, port=port)

    try:
        while True:
            data = await websocket.receive_bytes()
            logger.debug("ws.audio_received", bytes=len(data))

            # --- STT stage ---
            await _send_json(
                websocket,
                {
                    "type": "status",
                    "stage": "listening",
                    "bytes_received": len(data),
                },
            )

            stt_start = time.perf_counter()
            try:
                transcript = await speech_to_text(data, "stream.webm")
            except Exception:
                logger.exception("ws.stt_error", host=host, port=port)
                transcript = ""
            stt_ms = round((time.perf_counter() - stt_start) * 1000, 1)

            await _send_json(
                websocket,
                {
                    "type": "transcript",
                    "darja_text": transcript,
                    "latency_ms": stt_ms,
                },
            )

            if not transcript:
                continue

            # --- RAG generation stage ---
            await _send_json(
                websocket,
                {"type": "status", "stage": "processing"},
            )

            try:
                result = await generate(transcript)
            except Exception:
                logger.exception("ws.generation_error", host=host, port=port)
                result = {
                    "answer": "صارت مشكلة في المعالجة. حاول مرة أخرى.",
                    "hits": [],
                    "fallback": True,
                    "latency_ms": 0,
                }

            citations = [
                {
                    "source": hit.get("source", ""),
                    "article": hit.get("article", ""),
                    "content": hit.get("content", "")[:200],
                }
                for hit in result.get("hits", [])
            ]

            await _send_json(
                websocket,
                {
                    "type": "answer",
                    "text": result["answer"],
                    "citations": citations,
                    "fallback": result.get("fallback", False),
                    "latency_ms": result.get("latency_ms", 0),
                },
            )

            # --- TTS stage ---
            await _send_json(
                websocket,
                {"type": "status", "stage": "speaking"},
            )

            try:
                async for chunk in tts_stage(result["answer"]):
                    await websocket.send_bytes(chunk)
            except Exception:
                logger.exception("ws.tts_error", host=host, port=port)

            await _send_json(
                websocket,
                {"type": "status", "stage": "idle"},
            )

    except WebSocketDisconnect:
        logger.info("ws.disconnected", host=host, port=port)
