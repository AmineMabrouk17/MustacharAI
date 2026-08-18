"""WebSocket endpoint for real-time voice pipeline streaming."""

from __future__ import annotations

import json
import time

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mustachar.pipeline.stt import speech_to_text

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
      - Server responds with a ``status`` message acknowledging receipt.
      - Server runs STT and responds with a ``transcript`` message containing
        the recognised Darja text and the STT latency.
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

            await _send_json(
                websocket,
                {
                    "type": "status",
                    "stage": "listening",
                    "bytes_received": len(data),
                },
            )

            start = time.perf_counter()
            try:
                transcript = await speech_to_text(data, "stream.webm")
            except Exception:
                logger.exception("ws.stt_error", host=host, port=port)
                transcript = ""
            latency_ms = round((time.perf_counter() - start) * 1000, 1)

            await _send_json(
                websocket,
                {
                    "type": "transcript",
                    "darja_text": transcript,
                    "latency_ms": latency_ms,
                },
            )

    except WebSocketDisconnect:
        logger.info("ws.disconnected", host=host, port=port)
