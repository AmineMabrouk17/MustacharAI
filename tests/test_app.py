"""Tests for the FastAPI application endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from mustachar.api.app import app
from mustachar.pipeline.orchestrator import PipelineResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _make_pipeline_result(
    transcript: str = "سؤال بالدارجة",
    answer: str = "جواب من القانون",
) -> PipelineResult:
    return PipelineResult(
        transcript=transcript,
        reformulated_query="استعلام بالفصحى",
        answer=answer,
        citations=[{"source": "a.pdf", "article": "المادة 1", "content": "نص القانون"}],
        fallback=False,
        stage_latencies_ms={
            "stt": 100.0,
            "reformulate": 50.0,
            "retrieve_generate": 200.0,
        },
        total_latency_ms=350.0,
    )


async def _fake_tts(text: str, voice: str = "ar") -> AsyncIterator[bytes]:
    yield b"\xff\xfb\x90\x00"
    yield b"\xff\xfb\x90\x01"


# ── Health endpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


# ── REST /api/v1/ask endpoint ───────────────────────────────────


@pytest.mark.asyncio
@patch("mustachar.api.app.run_pipeline", return_value=_make_pipeline_result())
async def test_ask_returns_pipeline_result(mock_pipeline: AsyncMock) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        resp = await c.post(
            "/api/v1/ask",
            files={"audio": ("clip.webm", b"fake-audio", "audio/webm")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "سؤال بالدارجة"
    assert body["answer"] == "جواب من القانون"
    assert body["fallback"] is False
    assert len(body["citations"]) == 1


# ── REST /api/v1/speak endpoint ─────────────────────────────────


@pytest.mark.asyncio
async def test_speak_returns_audio() -> None:
    async def _fake_stream() -> AsyncIterator[dict[str, Any]]:
        for chunk in [
            {"type": "audio", "data": b"\xff\xfb\x90\x00"},
            {"type": "audio", "data": b"\xff\xfb\x90\x01"},
        ]:
            yield chunk

    mock_comm = MagicMock()
    mock_comm.stream = _fake_stream

    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate", return_value=mock_comm
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            resp = await c.post("/api/v1/speak", json={"text": "marhaba"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"


@pytest.mark.asyncio
async def test_speak_rejects_empty_text() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        resp = await c.post("/api/v1/speak", json={"text": ""})
    assert resp.status_code == 422


# ── WebSocket /api/v1/stream ────────────────────────────────────


@patch("mustachar.api.websocket.tts_stage", new=_fake_tts)
@patch("mustachar.api.websocket.run_pipeline", return_value=_make_pipeline_result())
def test_ws_full_pipeline(mock_pipeline: AsyncMock) -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"\x00\x01\x02\xff")

        status = ws.receive_json()
        assert status["type"] == "status"
        assert status["stage"] == "listening"

        transcript = ws.receive_json()
        assert transcript["type"] == "transcript"
        assert transcript["darja_text"] == "سؤال بالدارجة"

        processing = ws.receive_json()
        assert processing["stage"] == "processing"

        answer = ws.receive_json()
        assert answer["type"] == "answer"
        assert answer["text"] == "جواب من القانون"

        speaking = ws.receive_json()
        assert speaking["stage"] == "speaking"

        audio1 = ws.receive_bytes()
        audio2 = ws.receive_bytes()
        assert audio1 == b"\xff\xfb\x90\x00"
        assert audio2 == b"\xff\xfb\x90\x01"

        idle = ws.receive_json()
        assert idle["stage"] == "idle"


@patch(
    "mustachar.api.websocket.run_pipeline", side_effect=RuntimeError("pipeline error")
)
def test_ws_error_returns_fallback(mock_pipeline: AsyncMock) -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"\x00\x01")
        ws.receive_json()  # status: listening
        transcript = ws.receive_json()
        assert transcript["darja_text"] == ""
        answer = ws.receive_json()
        assert answer["fallback"] is True


def test_ws_graceful_disconnect() -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"ping")
        ws.receive_json()
        ws.receive_json()
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"still alive")
        status = ws.receive_json()
        assert status["bytes_received"] == len(b"still alive")
