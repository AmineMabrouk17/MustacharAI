"""Tests for the WebSocket streaming endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import pytest
from starlette.testclient import TestClient

from mustachar.app import app
from mustachar.pipeline.orchestrator import PipelineResult


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _make_pipeline_result(
    transcript: str = "سؤال بالدارجة",
    answer: str = "جواب من القانون",
) -> PipelineResult:
    return PipelineResult(
        transcript=transcript,
        reformulated_query="استعلام بالفصحى",
        answer=answer,
        citations=[
            {"source": "a.pdf", "article": "المادة 1", "content": "نص القانون"}
        ],
        fallback=False,
        stage_latencies_ms={"stt": 100.0, "reformulate": 50.0, "retrieve_generate": 200.0},
        total_latency_ms=350.0,
    )


async def _fake_tts_stage(text: str, voice: str = "ar") -> AsyncIterator[bytes]:
    yield b"\xff\xfb\x90\x00"
    yield b"\xff\xfb\x90\x01"


@patch("mustachar.api.websocket.tts_stage", new=_fake_tts_stage)
@patch(
    "mustachar.api.websocket.run_pipeline",
    return_value=_make_pipeline_result(),
)
def test_ws_full_pipeline_sends_transcript_and_answer(
    mock_pipeline: AsyncMock,
    client: TestClient,
) -> None:
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"\x00\x01\x02\xff")

        # Status: listening
        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["stage"] == "listening"

        # Transcript
        transcript_msg = ws.receive_json()
        assert transcript_msg["type"] == "transcript"
        assert transcript_msg["darja_text"] == "سؤال بالدارجة"
        assert transcript_msg["reformulated_query"] == "استعلام بالفصحى"
        assert "latency_ms" in transcript_msg

        # Status: processing
        processing_msg = ws.receive_json()
        assert processing_msg["type"] == "status"
        assert processing_msg["stage"] == "processing"

        # Answer
        answer_msg = ws.receive_json()
        assert answer_msg["type"] == "answer"
        assert answer_msg["text"] == "جواب من القانون"
        assert answer_msg["fallback"] is False
        assert len(answer_msg["citations"]) == 1
        assert "stage_latencies_ms" in answer_msg

        # Status: speaking
        speaking_msg = ws.receive_json()
        assert speaking_msg["type"] == "status"
        assert speaking_msg["stage"] == "speaking"

        # TTS binary audio chunks
        audio1 = ws.receive_bytes()
        assert audio1 == b"\xff\xfb\x90\x00"
        audio2 = ws.receive_bytes()
        assert audio2 == b"\xff\xfb\x90\x01"

        # Status: idle
        idle_msg = ws.receive_json()
        assert idle_msg["type"] == "status"
        assert idle_msg["stage"] == "idle"


@patch(
    "mustachar.api.websocket.run_pipeline",
    return_value=PipelineResult(
        transcript="",
        answer="",
        fallback=True,
    ),
)
def test_ws_empty_transcript_skips_generation(
    mock_pipeline: AsyncMock,
    client: TestClient,
) -> None:
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"\x00\x01")

        # Status: listening
        ws.receive_json()

        # Transcript (empty)
        transcript_msg = ws.receive_json()
        assert transcript_msg["darja_text"] == ""

        # No processing or answer messages


@patch(
    "mustachar.api.websocket.run_pipeline",
    side_effect=RuntimeError("pipeline exploded"),
)
def test_ws_pipeline_error_sends_fallback(
    mock_pipeline: AsyncMock,
    client: TestClient,
) -> None:
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"\x00\x01")

        # Status: listening
        ws.receive_json()

        # Transcript fallback
        transcript_msg = ws.receive_json()
        assert transcript_msg["type"] == "transcript"
        assert transcript_msg["darja_text"] == ""

        # Answer fallback
        answer_msg = ws.receive_json()
        assert answer_msg["type"] == "answer"
        assert answer_msg["fallback"] is True


@patch("mustachar.api.websocket.tts_stage", new=_fake_tts_stage)
@patch(
    "mustachar.api.websocket.run_pipeline",
    return_value=_make_pipeline_result(),
)
def test_ws_echo_multiple_frames(
    mock_pipeline: AsyncMock,
    client: TestClient,
) -> None:
    with client.websocket_connect("/api/v1/stream") as ws:
        for i in range(3):
            payload = bytes([i]) * 64
            ws.send_bytes(payload)

            # Status: listening
            status_msg = ws.receive_json()
            assert status_msg["type"] == "status"
            assert status_msg["bytes_received"] == len(payload)

            # Transcript
            transcript_msg = ws.receive_json()
            assert transcript_msg["type"] == "transcript"

            # Status: processing
            ws.receive_json()

            # Answer
            answer_msg = ws.receive_json()
            assert answer_msg["type"] == "answer"

            # Status: speaking
            ws.receive_json()

            # TTS audio chunks
            ws.receive_bytes()
            ws.receive_bytes()

            # Status: idle
            ws.receive_json()


def test_ws_graceful_disconnect(client: TestClient) -> None:
    # First connection session
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"ping")
        ws.receive_json()  # status
        ws.receive_json()  # transcript
    # Exiting 'with' block sends close frame cleanly

    # Second connection session to verify server handles re-connection cleanly
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"still alive")
        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["bytes_received"] == len(b"still alive")
        ws.receive_json()  # transcript


# ── Health endpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_200() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_returns_healthy_status() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/health")
    assert resp.json() == {"status": "healthy"}


# ── REST /api/v1/ask endpoint ───────────────────────────────────


@pytest.mark.asyncio
@patch(
    "mustachar.api.app.run_pipeline",
    return_value=PipelineResult(
        transcript="مرحبا",
        reformulated_query="تحية",
        answer="أهلا وسهلا",
        citations=[{"source": "a.pdf", "article": "المادة 1", "content": "نص"}],
        fallback=False,
        stage_latencies_ms={"stt": 100.0, "reformulate": 50.0, "retrieve_generate": 200.0},
        total_latency_ms=350.0,
    ),
)
async def test_ask_returns_full_pipeline_result(mock_pipeline: object) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            "/api/v1/ask",
            files={"audio": ("clip.webm", b"fake-audio", "audio/webm")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "مرحبا"
    assert body["reformulated_query"] == "تحية"
    assert body["answer"] == "أهلا وسهلا"
    assert body["fallback"] is False
    assert len(body["citations"]) == 1
    assert "stage_latencies_ms" in body
    assert "total_latency_ms" in body
