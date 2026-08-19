"""Tests for the RAG pipeline stages."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mustachar.pipeline.generator import FALLBACK_DARJA, _build_context_block, generate
from mustachar.pipeline.ingestion import chunk_by_articles, parse_pdf
from mustachar.pipeline.orchestrator import (
    FALLBACK_GENERATE,
    FALLBACK_STT,
    PipelineResult,
    run_pipeline,
)
from mustachar.pipeline.reformulator import FALLBACK_RESULT, reformulate
from mustachar.pipeline.retrieval import RETRIEVAL_THRESHOLD, retrieve
from mustachar.pipeline.stt import speech_to_text

# ── Ingestion ───────────────────────────────────────────────────

SAMPLE_TEXT = """\
ال法则 العامة
المادة 1 - هذا القانون ينظم hoạtت المحاكم.
المادة 2 - تطبق أحكام هذا القانون على جميع الموظفين.
المادة 3 - يُعدّ مخالفاً من حادث على هذه الأحكام.
"""


def test_chunk_by_articles() -> None:
    chunks = chunk_by_articles(SAMPLE_TEXT)
    assert len(chunks) == 4
    assert chunks[0]["article"] == "مقدمة"
    assert len([c for c in chunks if c["article"].startswith("المادة")]) == 3


def test_chunk_by_articles_empty() -> None:
    assert chunk_by_articles("") == []


def test_parse_pdf(tmp_path: Any) -> None:
    from pypdf import PdfWriter

    pdf_path = tmp_path / "test.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    assert isinstance(parse_pdf(pdf_path), str)


# ── Retrieval ───────────────────────────────────────────────────


def _mock_query_result(
    documents: list[str] | None = None,
    metadatas: list[dict[str, Any]] | None = None,
    distances: list[float] | None = None,
) -> dict[str, Any]:
    return {
        "documents": [documents or []],
        "metadatas": [metadatas or []],
        "distances": [distances or []],
    }


@patch("mustachar.pipeline.retrieval.get_or_create_collection")
@patch("mustachar.pipeline.retrieval.get_chroma_client")
def test_retrieve_filters_by_threshold(
    mock_client: MagicMock, mock_col: MagicMock
) -> None:
    collection = MagicMock()
    collection.query.return_value = _mock_query_result(
        documents=["close", "far"],
        metadatas=[
            {"source": "a.pdf", "article": "المادة 1", "category": ""},
            {"source": "b.pdf", "article": "المادة 2", "category": ""},
        ],
        distances=[0.5, 0.9],
    )
    mock_col.return_value = collection

    hits = retrieve("query")
    assert len(hits) == 1
    assert hits[0]["distance"] == 0.5


def test_default_threshold() -> None:
    assert RETRIEVAL_THRESHOLD == 0.65


# ── Generator ───────────────────────────────────────────────────


def test_build_context_block() -> None:
    hits: list[dict[str, Any]] = [
        {
            "content": "نص القانون",
            "source": "a.pdf",
            "article": "المادة 1",
            "category": "",
            "distance": 0.3,
        },
    ]
    block = _build_context_block(hits)
    assert "[1]" in block
    assert "a.pdf" in block


@pytest.mark.asyncio
@patch("mustachar.pipeline.generator.retrieve", return_value=[])
async def test_generate_fallback_on_no_hits(mock_retrieve: AsyncMock) -> None:
    result = await generate("سؤال")
    assert result["fallback"] is True
    assert result["answer"] == FALLBACK_DARJA


@pytest.mark.asyncio
@patch("mustachar.pipeline.generator.chat", return_value="جواب من القانون")
@patch(
    "mustachar.pipeline.generator.retrieve",
    return_value=[
        {
            "content": "نص",
            "source": "a.pdf",
            "article": "المادة 1",
            "category": "",
            "distance": 0.3,
        }
    ],
)
async def test_generate_returns_grounded_answer(
    mock_retrieve: AsyncMock, mock_chat: AsyncMock
) -> None:
    result = await generate("ما هو القانون؟")
    assert result["fallback"] is False
    assert result["answer"] == "جواب من القانون"
    mock_chat.assert_awaited_once()


# ── Reformulator ────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("mustachar.pipeline.reformulator.chat_json")
async def test_reformulate_returns_structured_output(mock_chat: AsyncMock) -> None:
    mock_chat.return_value = json.dumps(
        {"primary_query": "droit en Tunisie", "keywords": ["droit"]}
    )
    result = await reformulate("كيفاش القانون في تونس؟")
    assert result["primary_query"] != ""
    assert isinstance(result["keywords"], list)


@pytest.mark.asyncio
async def test_reformulate_empty_returns_fallback() -> None:
    result = await reformulate("")
    assert result["primary_query"] == FALLBACK_RESULT["primary_query"]


# ── STT ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("mustachar.pipeline.stt.transcribe", return_value="أهلا")
async def test_speech_to_text(mock_transcribe: AsyncMock) -> None:
    result = await speech_to_text(b"fake-audio", "clip.webm")
    assert result == "أهلا"


# ── Orchestrator ────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_pipeline_full_success(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.return_value = "كيفاش القانون؟"
    mock_reformulate.return_value = {
        "primary_query": "القانون",
        "keywords": [],
        "latency_ms": 50.0,
    }
    mock_generate.return_value = {
        "answer": "جواب",
        "hits": [],
        "fallback": False,
        "latency_ms": 100.0,
    }

    result = await run_pipeline(b"\x00\x01", "test.webm")
    assert result.transcript == "كيفاش القانون؟"
    assert result.answer == "جواب"
    assert result.fallback is False


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_pipeline_stt_failure(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.side_effect = RuntimeError("error")
    result = await run_pipeline(b"\x00\x01", "test.webm")
    assert result.answer == FALLBACK_STT
    assert result.fallback is True
    mock_reformulate.assert_not_called()


def test_fallback_messages_are_arabic() -> None:
    assert "ما فهمتش" in FALLBACK_STT
    assert "ما لقيتش" in FALLBACK_GENERATE


def test_pipeline_result_defaults() -> None:
    result = PipelineResult()
    assert result.transcript == ""
    assert result.fallback is True
