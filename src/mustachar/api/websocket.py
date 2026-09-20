"""WebSocket endpoint for text chat pipeline streaming."""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mustachar.pipeline.orchestrator import run_pipeline

router = APIRouter()
logger = structlog.get_logger()


async def _send_json(websocket: WebSocket, payload: dict[str, object]) -> None:
    """Send a JSON message over the WebSocket."""
    await websocket.send_text(json.dumps(payload))


@router.websocket("/api/v1/stream")
async def stream(websocket: WebSocket) -> None:
    """Accept a WebSocket connection for the text chat pipeline.

    Protocol:
      - Client sends ``{"type": "chat", "message": "<question>"}``.
      - Server sends ``status`` messages for ``processing``/``idle`` and a final
        ``answer`` message with the grounded response and legal citations.
    """
    await websocket.accept()
    client = websocket.client
    host = client.host if client else "unknown"
    port = client.port if client else 0
    logger.info("ws.connected", host=host, port=port)

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

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

            if payload.get("type") != "chat":
                continue

            question = str(payload.get("message", "")).strip()
            if not question:
                await _send_json(websocket, {"type": "status", "stage": "idle"})
                continue

            await _send_json(websocket, {"type": "status", "stage": "processing"})

            try:
                result = await run_pipeline(question)
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
            await _send_json(websocket, {"type": "status", "stage": "idle"})

    except WebSocketDisconnect:
        logger.info("ws.disconnected", host=host, port=port)