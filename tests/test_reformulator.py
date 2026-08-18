"""Tests for the query reformulator pipeline stage."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from mustachar.pipeline.reformulator import FALLBACK_RESULT, SYSTEM_PROMPT, reformulate


@pytest.mark.asyncio
@patch(
    "mustachar.pipeline.reformulator.chat_json",
    return_value=json.dumps(
        {
            "primary_query": "ال绞اع القانوني في Tunisia",
            "keywords": ["قانون", "绞اع", "تونس"],
        }
    ),
)
async def test_reformulate_returns_structured_output(mock_chat: AsyncMock) -> None:
    result = await reformulate("كيفاش ي Services القانون في تونس؟")

    assert result["primary_query"] != ""
    assert isinstance(result["keywords"], list)
    assert len(result["keywords"]) >= 2
    assert "latency_ms" in result


@pytest.mark.asyncio
@patch("mustachar.pipeline.reformulator.chat_json")
async def test_reformulate_passes_correct_messages(mock_chat: AsyncMock) -> None:
    mock_chat.return_value = json.dumps(
        {"primary_query": "استعلام", "keywords": ["كلمة"]}
    )

    await reformulate("سؤال بالدارجة")

    call_args = mock_chat.call_args
    messages = call_args[0][0]

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "سؤال بالدارجة"


@pytest.mark.asyncio
@patch("mustachar.pipeline.reformulator.chat_json")
async def test_reformulate_uses_json_format(mock_chat: AsyncMock) -> None:
    mock_chat.return_value = json.dumps({"primary_query": "x", "keywords": ["y"]})

    await reformulate("test")

    call_kwargs = mock_chat.call_args[1]
    assert call_kwargs.get("max_tokens") == 35


@pytest.mark.asyncio
async def test_reformulate_empty_query_returns_fallback() -> None:
    result = await reformulate("")

    assert result["primary_query"] == FALLBACK_RESULT["primary_query"]
    assert result["keywords"] == FALLBACK_RESULT["keywords"]
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_reformulate_whitespace_query_returns_fallback() -> None:
    result = await reformulate("   ")

    assert result["primary_query"] == ""


@pytest.mark.asyncio
@patch("mustachar.pipeline.reformulator.chat_json", return_value="not json")
async def test_reformulate_invalid_json_returns_fallback(mock_chat: AsyncMock) -> None:
    result = await reformulate("سؤال")

    assert result["primary_query"] == FALLBACK_RESULT["primary_query"]
    assert result["keywords"] == FALLBACK_RESULT["keywords"]


@pytest.mark.asyncio
@patch("mustachar.pipeline.reformulator.chat_json")
async def test_reformulate_non_list_keywords_normalized(mock_chat: AsyncMock) -> None:
    mock_chat.return_value = json.dumps(
        {"primary_query": "test", "keywords": "not-a-list"}
    )

    result = await reformulate("question")

    assert result["keywords"] == []


@pytest.mark.asyncio
@patch("mustachar.pipeline.reformulator.chat_json")
async def test_reformulate_logs_latency(mock_chat: AsyncMock) -> None:
    mock_chat.return_value = json.dumps({"primary_query": "x", "keywords": ["y"]})

    result = await reformulate("test")

    assert isinstance(result["latency_ms"], float)


def test_fallback_result_structure() -> None:
    assert FALLBACK_RESULT["primary_query"] == ""
    assert FALLBACK_RESULT["keywords"] == []
