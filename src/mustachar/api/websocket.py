"""WebSocket endpoint for real-time voice pipeline streaming."""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mustachar.pipeline.orchestrator import run_pipeline
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
      - Server runs STT → Reformulate → Retrieve → Generate → TTS and sends:
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
            logger.info("ws.audio_received", host=host, port=port, bytes=len(data))

            # --- Pipeline stages: STT → Reformulate → Retrieve → Generate ---
            await _send_json(
                websocket,
                {
                    "type": "status",
                    "stage": "listening",
                    "bytes_received": len(data),
                },
            )

            try:
                result = await run_pipeline(data, "stream.webm")
            except Exception:
                logger.exception("ws.pipeline_error", host=host, port=port)
                await _send_json(
                    websocket,
                    {
                        "type": "transcript",
                        "darja_text": "",
                        "reformulated_query": "",
                        "latency_ms": 0,
                    },
                )
                await _send_json(
                    websocket,
                    {
                        "type": "answer",
                        "text": "صارت مشكلة في المعالجة. حاول مرة أخرى.",
                        "citations": [],
                        "fallback": True,
                        "latency_ms": 0,
                        "stage_latencies_ms": {},
                    },
                )
                continue

            await _send_json(
                websocket,
                {
                    "type": "transcript",
                    "darja_text": result.transcript,
                    "reformulated_query": result.reformulated_query,
                    "latency_ms": result.stage_latencies_ms.get("stt", 0),
                },
            )

            if not result.transcript:
                continue

            await _send_json(
                websocket,
                {
                    "type": "status",
                    "stage": "processing",
                },
            )

            await _send_json(
                websocket,
                {
                    "type": "answer",
                    "text": result.answer,
                    "citations": result.citations,
                    "fallback": result.fallback,
                    "latency_ms": result.stage_latencies_ms.get(
                        "retrieve_generate", 0
                    ),
                    "stage_latencies_ms": result.stage_latencies_ms,
                },
            )

            # --- TTS stage ---
            await _send_json(
                websocket,
                {"type": "status", "stage": "speaking"},
            )

            try:
                audio_parts: list[bytes] = []
                async for chunk in tts_stage(result.answer):
                    audio_parts.append(chunk)
                if audio_parts:
                    await websocket.send_bytes(b"".join(audio_parts))
            except Exception:
                logger.exception("ws.tts_error", host=host, port=port)

            await _send_json(
                websocket,
                {"type": "status", "stage": "idle"},
            )

    except WebSocketDisconnect:
        logger.info("ws.disconnected", host=host, port=port)
