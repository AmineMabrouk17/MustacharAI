"""Tests for the full RAG pipeline orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mustachar.pipeline.orchestrator import (
    FALLBACK_GENERATE,
    FALLBACK_REFORMULATE,
    FALLBACK_STT,
    FALLBACK_TTS,
    PipelineResult,
    run_pipeline,
)


def test_pipeline_result_default_values() -> None:
    result = PipelineResult()
    assert result.transcript == ""
    assert result.reformulated_query == ""
    assert result.answer == ""
    assert result.citations == []
    assert result.fallback is True
    assert result.stage_latencies_ms == {}
    assert result.total_latency_ms == 0.0


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_run_pipeline_full_success(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.return_value = "كيفاش القانون في تونس؟"
    mock_reformulate.return_value = {
        "primary_query": "القانون في تونس",
        "keywords": ["قانون", "تونس"],
        "latency_ms": 150.0,
    }
    mock_generate.return_value = {
        "answer": "القانون في تونس ينص على ذلك في المادة 1",
        "hits": [
            {
                "content": "نص القانون",
                "source": "majalla1.pdf",
                "article": "المادة 1",
                "category": "",
                "distance": 0.3,
            }
        ],
        "fallback": False,
        "latency_ms": 300.0,
    }

    result = await run_pipeline(b"\x00\x01", "test.webm")

    assert result.transcript == "كيفاش القانون في تونس؟"
    assert result.reformulated_query == "القانون في تونس"
    assert result.answer == "القانون في تونس ينص على ذلك في المادة 1"
    assert result.fallback is False
    assert len(result.citations) == 1
    assert result.citations[0]["source"] == "majalla1.pdf"
    assert result.citations[0]["article"] == "المادة 1"
    assert result.citations[0]["content"] == "نص القانون"
    assert "stt" in result.stage_latencies_ms
    assert "reformulate" in result.stage_latencies_ms
    assert "retrieve_generate" in result.stage_latencies_ms
    assert result.total_latency_ms >= 0


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_run_pipeline_stt_failure_returns_fallback(
    mock_stt: AsyncMock,
    mock_generate: AsyncMock,
    mock_reformulate: AsyncMock,
) -> None:
    mock_stt.side_effect = RuntimeError("Groq API error")

    result = await run_pipeline(b"\x00\x01", "test.webm")

    assert result.transcript == ""
    assert result.answer == FALLBACK_STT
    assert result.fallback is True
    assert "stt" in result.stage_latencies_ms
    mock_reformulate.assert_not_called()
    mock_generate.assert_not_called()


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_run_pipeline_empty_transcript_returns_fallback(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.return_value = ""

    result = await run_pipeline(b"\x00\x01", "test.webm")

    assert result.transcript == ""
    assert result.answer == FALLBACK_STT
    mock_reformulate.assert_not_called()
    mock_generate.assert_not_called()


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_run_pipeline_reformulate_failure_uses_raw_transcript(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.return_value = "سؤال بالدارجة"
    mock_reformulate.side_effect = RuntimeError("Groq timeout")
    mock_generate.return_value = {
        "answer": "جواب من القانون",
        "hits": [],
        "fallback": False,
        "latency_ms": 100.0,
    }

    result = await run_pipeline(b"\x00\x01", "test.webm")

    assert result.transcript == "سؤال بالدارجة"
    assert result.reformulated_query == ""
    assert "reformulate" in result.stage_latencies_ms
    mock_generate.assert_awaited_once_with("سؤال بالدارجة")


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_run_pipeline_generate_failure_returns_fallback(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.return_value = "سؤال"
    mock_reformulate.return_value = {
        "primary_query": "استعلام",
        "keywords": [],
        "latency_ms": 50.0,
    }
    mock_generate.side_effect = RuntimeError("Groq API error")

    result = await run_pipeline(b"\x00\x01", "test.webm")

    assert result.answer == FALLBACK_GENERATE
    assert result.fallback is True
    assert result.citations == []
    assert "retrieve_generate" in result.stage_latencies_ms


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_run_pipeline_uses_reformulated_query_for_generation(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.return_value = "كيفاش نعمل فاتورة؟"
    mock_reformulate.return_value = {
        "primary_query": "إصدار الفواتير القانونية",
        "keywords": ["فاتورة", "قانون"],
        "latency_ms": 100.0,
    }
    mock_generate.return_value = {
        "answer": "جواب",
        "hits": [],
        "fallback": False,
        "latency_ms": 200.0,
    }

    await run_pipeline(b"\x00\x01", "test.webm")

    mock_generate.assert_awaited_once_with("إصدار الفواتير القانونية")


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_run_pipeline_reformulate_empty_primary_uses_raw_transcript(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.return_value = "سؤال بالدارجة"
    mock_reformulate.return_value = {
        "primary_query": "",
        "keywords": [],
        "latency_ms": 50.0,
    }
    mock_generate.return_value = {
        "answer": "جواب",
        "hits": [],
        "fallback": False,
        "latency_ms": 100.0,
    }

    await run_pipeline(b"\x00\x01", "test.webm")

    mock_generate.assert_awaited_once_with("سؤال بالدارجة")


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_run_pipeline_citations_truncated_to_200_chars(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.return_value = "سؤال"
    mock_reformulate.return_value = {
        "primary_query": "استعلام",
        "keywords": [],
        "latency_ms": 50.0,
    }
    long_content = "أ" * 300
    mock_generate.return_value = {
        "answer": "جواب",
        "hits": [
            {
                "content": long_content,
                "source": "test.pdf",
                "article": "المادة 1",
                "category": "",
                "distance": 0.3,
            }
        ],
        "fallback": False,
        "latency_ms": 100.0,
    }

    result = await run_pipeline(b"\x00\x01", "test.webm")

    assert len(result.citations[0]["content"]) == 200


@pytest.mark.asyncio
@patch("mustachar.pipeline.orchestrator.generate")
@patch("mustachar.pipeline.orchestrator.reformulate")
@patch("mustachar.pipeline.orchestrator.speech_to_text")
async def test_run_pipeline_tracks_total_latency(
    mock_stt: AsyncMock,
    mock_reformulate: AsyncMock,
    mock_generate: AsyncMock,
) -> None:
    mock_stt.return_value = "سؤال"
    mock_reformulate.return_value = {
        "primary_query": "استعلام",
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

    assert result.total_latency_ms >= 0
    assert result.stage_latencies_ms["stt"] >= 0
    assert result.stage_latencies_ms["reformulate"] >= 0
    assert result.stage_latencies_ms["retrieve_generate"] >= 0


def test_fallback_messages_are_arabic() -> None:
    assert "ما فهمتش" in FALLBACK_STT
    assert "ما نجمتش" in FALLBACK_REFORMULATE
    assert "ما لقيتش" in FALLBACK_GENERATE
    assert "مشكلة" in FALLBACK_TTS
