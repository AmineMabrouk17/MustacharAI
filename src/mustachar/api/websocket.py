"""WebSocket endpoint for real-time audio streaming."""

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = structlog.get_logger()


@router.websocket("/api/v1/stream")
async def stream(websocket: WebSocket) -> None:
    """Accept a WebSocket connection and echo binary audio frames back."""
    await websocket.accept()
    client = websocket.client
    host = client.host if client else "unknown"
    port = client.port if client else 0
    logger.info("ws.connected", host=host, port=port)

    try:
        while True:
            data = await websocket.receive_bytes()
            await websocket.send_bytes(data)
            logger.debug("ws.echoed", bytes=len(data))
    except WebSocketDisconnect:
        logger.info("ws.disconnected", host=host, port=port)
