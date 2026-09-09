"""Tests for the FastAPI application endpoints."""

from __future__ import annotations

import array
import asyncio
import threading
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from mustachar.api.app import app
from mustachar.pipeline.orchestrator import PipelineResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Raw 16 kHz / 16-bit / mono PCM fixtures matching the streaming protocol. One
# VAD frame is 30 ms = 480 samples = 960 bytes.
_SPEECH_FRAME = array.array("h", [1500] * 480).tobytes()
_SILENCE_FRAME = bytes(960)


def _make_pipeline_result(
    transcript: str = "سؤال بالدارجة",
    answer: str = "جواب من القانون",
) -> PipelineResult:
    return PipelineResult(
        transcript=transcript,
        reformulated_query="استعلام بالفصحى",
        answer=answer,
        citations=[
            {
                "source": "a.pdf",
                "article": "المادة 1",
                "content": "نص القانون",
                "category": "مجلة الشغل",
            }
        ],
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
    assert body["citations"][0]["category"] == "مجلة الشغل"


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

    with (
        patch(
            "mustachar.infra.edge_tts_client._available_voice_names",
            new_callable=AsyncMock,
            return_value=frozenset({"fr-FR-HenriNeural"}),
        ),
        patch(
            "mustachar.infra.edge_tts_client.edge_tts.Communicate",
            return_value=mock_comm,
        ),
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

# A turn: 4 speech frames to open the utterance, then 16 silence frames
# (500 ms) which makes the VAD emit the completed segment.
_TURN_PCM = _SPEECH_FRAME * 4 + _SILENCE_FRAME * 16


@patch("mustachar.api.websocket.tts_stage", new=_fake_tts)
@patch(
    "mustachar.api.websocket.run_pipeline_from_transcript",
    return_value=_make_pipeline_result(),
)
@patch("mustachar.api.websocket.transcribe_pcm_segment", return_value="مرحبا")
def test_ws_streams_partial_transcript_then_pipeline(
    mock_transcribe: AsyncMock, mock_pipeline: AsyncMock
) -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(_TURN_PCM)

        partial = ws.receive_json()
        assert partial["type"] == "transcript"
        assert partial["partial"] is True
        assert partial["darja_text"] == "مرحبا"

        ws.send_json({"type": "end"})

        final_transcript = ws.receive_json()
        assert final_transcript["type"] == "transcript"
        assert final_transcript["partial"] is False
        assert final_transcript["darja_text"] == "مرحبا"

        processing = ws.receive_json()
        assert processing["stage"] == "processing"

        answer = ws.receive_json()
        assert answer["type"] == "answer"
        assert answer["text"] == "جواب من القانون"

        speaking = ws.receive_json()
        assert speaking["stage"] == "speaking"

        first_part = ws.receive_bytes()
        assert first_part == b"\xff\xfb\x90\x00"
        second_part = ws.receive_bytes()
        assert second_part == b"\xff\xfb\x90\x01"

        idle = ws.receive_json()
        assert idle["stage"] == "idle"

    mock_transcribe.assert_awaited_once()
    mock_pipeline.assert_awaited_once_with("مرحبا")


def test_ws_streams_audio_part_before_synthesis_finishes() -> None:
    gate = threading.Event()

    async def _blocking_tts(text: str, voice: str = "ar") -> AsyncIterator[bytes]:
        yield b"first-part"
        await asyncio.to_thread(gate.wait)
        yield b"second-part"

    mock_pipeline = AsyncMock(return_value=_make_pipeline_result())
    with (
        patch("mustachar.api.websocket.tts_stage", new=_blocking_tts),
        patch(
            "mustachar.api.websocket.run_pipeline_from_transcript", new=mock_pipeline
        ),
        patch("mustachar.api.websocket.transcribe_pcm_segment", return_value="مرحبا"),
    ):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/stream") as ws:
            ws.send_bytes(_TURN_PCM)
            ws.receive_json()  # partial transcript

            ws.send_json({"type": "end"})

            ws.receive_json()  # final transcript
            ws.receive_json()  # processing
            ws.receive_json()  # answer
            ws.receive_json()  # speaking

            # The pipeline is still synthesising (the fake TTS is blocked on the
            # gate and has not yielded its second part), so the first part can
            # only have arrived because the backend streams chunks as produced.
            assert ws.receive_bytes() == b"first-part"
            gate.set()

            assert ws.receive_bytes() == b"second-part"
            idle = ws.receive_json()
            assert idle["stage"] == "idle"


@patch(
    "mustachar.api.websocket.run_pipeline_from_transcript",
    side_effect=RuntimeError("pipeline error"),
)
@patch("mustachar.api.websocket.transcribe_pcm_segment", return_value="مرحبا")
def test_ws_pipeline_error_returns_fallback(
    mock_transcribe: AsyncMock, mock_pipeline: AsyncMock
) -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(_TURN_PCM)
        ws.receive_json()  # partial transcript

        ws.send_json({"type": "end"})

        final_transcript = ws.receive_json()
        assert final_transcript["type"] == "transcript"
        assert final_transcript["partial"] is False

        processing = ws.receive_json()
        assert processing["stage"] == "processing"

        answer = ws.receive_json()
        assert answer["type"] == "answer"
        assert answer["fallback"] is True


def test_ws_empty_turn_returns_idle() -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_json({"type": "end"})
        status = ws.receive_json()
        assert status["type"] == "status"
        assert status["stage"] == "idle"


def test_ws_graceful_disconnect() -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"still alive")
        ws.send_json({"type": "end"})
        status = ws.receive_json()
        assert status["type"] == "status"
