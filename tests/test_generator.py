"""Tests for the grounded reasoning generator pipeline stage."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from mustachar.pipeline.generator import (
    FALLBACK_DARJA,
    SYSTEM_PROMPT,
    _build_context_block,
    generate,
)


def test_build_context_block_formats_hits() -> None:
    hits: list[dict[str, Any]] = [
        {
            "content": "نص القانون",
            "source": "majalla1.pdf",
            "article": "المادة 1",
            "category": "قانون",
            "distance": 0.3,
        },
    ]
    block = _build_context_block(hits)

    assert "[1]" in block
    assert "majalla1.pdf" in block
    assert "المادة 1" in block
    assert "نص القانون" in block


def test_build_context_block_multiple_hits() -> None:
    hits: list[dict[str, Any]] = [
        {
            "content": "أول",
            "source": "a.pdf",
            "article": "المادة 1",
            "category": "",
            "distance": 0.2,
        },
        {
            "content": "ثاني",
            "source": "b.pdf",
            "article": "المادة 5",
            "category": "",
            "distance": 0.4,
        },
    ]
    block = _build_context_block(hits)

    assert "[1]" in block
    assert "[2]" in block
    assert "أول" in block
    assert "ثاني" in block


@pytest.mark.asyncio
@patch("mustachar.pipeline.generator.retrieve", return_value=[])
async def test_generate_returns_fallback_when_no_hits(
    mock_retrieve: AsyncMock,
) -> None:
    result = await generate("سؤال بلا سياق")

    assert result["fallback"] is True
    assert result["answer"] == FALLBACK_DARJA
    assert result["hits"] == []
    mock_retrieve.assert_called_once()


@pytest.mark.asyncio
@patch("mustachar.pipeline.generator.chat", return_value="القانون ينص على ذلك في المادة 1")
@patch(
    "mustachar.pipeline.generator.retrieve",
    return_value=[
        {
            "content": "نص القانون",
            "source": "majalla1.pdf",
            "article": "المادة 1",
            "category": "",
            "distance": 0.3,
        }
    ],
)
async def test_generate_returns_grounded_answer(
    mock_retrieve: AsyncMock,
    mock_chat: AsyncMock,
) -> None:
    result = await generate("ما هو القانون؟")

    assert result["fallback"] is False
    assert result["answer"] == "القانون ينص على ذلك في المادة 1"
    assert len(result["hits"]) == 1
    mock_chat.assert_awaited_once()


@pytest.mark.asyncio
@patch("mustachar.pipeline.generator.chat", return_value="جواب")
@patch(
    "mustachar.pipeline.generator.retrieve",
    return_value=[
        {
            "content": "نص",
            "source": "a.pdf",
            "article": "المادة 2",
            "category": "",
            "distance": 0.5,
        }
    ],
)
async def test_generate_passes_correct_messages_to_chat(
    mock_retrieve: AsyncMock,
    mock_chat: AsyncMock,
) -> None:
    await generate("سؤال")

    call_args = mock_chat.call_args
    messages = call_args[0][0]

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert messages[1]["role"] == "user"
    assert "سؤال" in messages[1]["content"]
    assert "المادة 2" in messages[1]["content"]


@pytest.mark.asyncio
@patch("mustachar.pipeline.generator.retrieve", return_value=[])
async def test_generate_logs_latency(mock_retrieve: AsyncMock) -> None:
    result = await generate("test")

    assert "latency_ms" in result
    assert isinstance(result["latency_ms"], float)


def test_fallback_message_is_arabic() -> None:
    assert "ما لقيتش" in FALLBACK_DARJA
