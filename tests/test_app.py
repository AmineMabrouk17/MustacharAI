"""Tests for the FastAPI application endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from mustachar.api.app import app
from mustachar.api.ratelimit import _hits
from mustachar.pipeline.orchestrator import PipelineResult


def _make_pipeline_result(
    question: str = "كيفاش القانون؟",
    answer: str = "جواب من القانون",
) -> PipelineResult:
    return PipelineResult(
        question=question,
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
            "reformulate": 50.0,
            "retrieve_generate": 200.0,
        },
        total_latency_ms=250.0,
    )


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
            json={"question": "كيفاش القانون؟"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "جواب من القانون"
    assert body["fallback"] is False
    assert len(body["citations"]) == 1
    assert body["citations"][0]["category"] == "مجلة الشغل"
    mock_pipeline.assert_awaited_once_with("كيفاش القانون؟")


# ── REST /api/v1/documents endpoints ───────────────────────────


@patch(
    "mustachar.api.app.list_indexed_documents",
    return_value=[{"source": "constitution", "articles_count": 149}],
)
async def test_get_documents(mock_list: MagicMock) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        resp = await c.get("/api/v1/documents")
    assert resp.status_code == 200
    assert resp.json() == [{"source": "constitution", "articles_count": 149}]


@patch(
    "mustachar.api.app.ingest_file_bytes",
    return_value={
        "filename": "loi.txt",
        "source": "loi",
        "articles_indexed": 12,
        "status": "success",
    },
)
async def test_upload_document_txt(mock_ingest: MagicMock) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        resp = await c.post(
            "/api/v1/documents/upload",
            files={"file": ("loi.txt", "الفصل 1\nنص", "text/plain")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["articles_indexed"] == 12
    assert body["status"] == "success"
    mock_ingest.assert_called_once()
    assert mock_ingest.call_args.args[1] == "loi.txt"


async def test_upload_document_rejects_unsupported_extension() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        resp = await c.post(
            "/api/v1/documents/upload",
            files={"file": ("malware.exe", b"\x00\x01", "application/octet-stream")},
        )
    assert resp.status_code == 400


@patch(
    "mustachar.api.app.ingest_file_bytes",
    side_effect=ValueError("تعذر استخراج أي نص"),
)
async def test_upload_document_returns_422_on_value_error(mock_ingest: MagicMock) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        resp = await c.post(
            "/api/v1/documents/upload",
            files={"file": ("bad.txt", "   ", "text/plain")},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ask_rejects_empty_question() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        resp = await c.post("/api/v1/ask", json={"question": ""})
    assert resp.status_code == 422


# ── WebSocket /api/v1/stream ────────────────────────────────────


@patch(
    "mustachar.api.websocket.run_pipeline",
    return_value=_make_pipeline_result(),
)
def test_ws_streams_answer(mock_pipeline: AsyncMock) -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_json({"type": "chat", "message": "كيفاش القانون؟"})

        processing = ws.receive_json()
        assert processing["stage"] == "processing"

        answer = ws.receive_json()
        assert answer["type"] == "answer"
        assert answer["text"] == "جواب من القانون"

        idle = ws.receive_json()
        assert idle["stage"] == "idle"

    mock_pipeline.assert_awaited_once_with("كيفاش القانون؟")


@patch(
    "mustachar.api.websocket.run_pipeline",
    side_effect=RuntimeError("pipeline error"),
)
def test_ws_pipeline_error_returns_fallback(mock_pipeline: AsyncMock) -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_json({"type": "chat", "message": "كيفاش القانون؟"})

        processing = ws.receive_json()
        assert processing["stage"] == "processing"

        answer = ws.receive_json()
        assert answer["type"] == "answer"
        assert answer["fallback"] is True


def test_ws_empty_turn_returns_idle() -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_json({"type": "chat", "message": "   "})
        status = ws.receive_json()
        assert status["type"] == "status"
        assert status["stage"] == "idle"


def test_ws_graceful_disconnect() -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"ignored binary")
        ws.send_json({"type": "chat", "message": "مرحبا"})
        status = ws.receive_json()
        assert status["type"] == "status"


def test_rate_limit_blocks_after_15_per_minute() -> None:
    _hits.clear()
    client = TestClient(app)
    codes = [client.get("/api/v1/stream").status_code for _ in range(15)]
    assert 429 not in codes
    assert client.get("/api/v1/stream").status_code == 429
    _hits.clear()


def test_rate_limit_passes_non_api_routes() -> None:
    _hits.clear()
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert _hits == {}
    _hits.clear()


def test_rate_limit_uses_cf_connecting_ip() -> None:
    _hits.clear()
    client = TestClient(app)
    codes = [
        client.get(
            "/api/v1/stream", headers={"CF-Connecting-IP": "1.2.3.4"}
        ).status_code
        for _ in range(15)
    ]
    assert 429 not in codes
    assert (
        client.get(
            "/api/v1/stream", headers={"CF-Connecting-IP": "1.2.3.4"}
        ).status_code
        == 429
    )
    # A different client IP is not blocked.
    assert client.get(
        "/api/v1/stream", headers={"CF-Connecting-IP": "5.6.7.8"}
    ).status_code in (404, 405)
    _hits.clear()
