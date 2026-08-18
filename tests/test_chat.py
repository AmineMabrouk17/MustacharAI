"""Tests for the Groq chat completion wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mustachar.infra.groq_client import chat, chat_json


@pytest.mark.asyncio
@patch("mustachar.infra.groq_client._get_client")
async def test_chat_returns_response_text(mock_get: AsyncMock) -> None:
    mock_message = MagicMock()
    mock_message.content = "القانون ينص على ذلك"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get.return_value = mock_client

    messages = [{"role": "user", "content": "ما هو القانون؟"}]
    result = await chat(messages)

    assert result == "القانون ينص على ذلك"
    mock_client.chat.completions.create.assert_awaited_once_with(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.3,
        max_tokens=1024,
    )


@pytest.mark.asyncio
@patch("mustachar.infra.groq_client._get_client")
async def test_chat_returns_empty_on_none_content(mock_get: AsyncMock) -> None:
    mock_message = MagicMock()
    mock_message.content = None
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get.return_value = mock_client

    result = await chat([{"role": "user", "content": "test"}])

    assert result == ""


@pytest.mark.asyncio
@patch("mustachar.infra.groq_client._get_client")
async def test_chat_custom_model_and_params(mock_get: AsyncMock) -> None:
    mock_message = MagicMock()
    mock_message.content = "ok"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get.return_value = mock_client

    await chat(
        [{"role": "user", "content": "hi"}],
        model="llama-3.1-8b-instant",
        temperature=0.7,
        max_tokens=256,
    )

    mock_client.chat.completions.create.assert_awaited_once_with(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        max_tokens=256,
    )


@pytest.mark.asyncio
@patch("mustachar.infra.groq_client._get_client")
async def test_chat_json_returns_json_string(mock_get: AsyncMock) -> None:
    mock_message = MagicMock()
    mock_message.content = '{"key": "value"}'
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get.return_value = mock_client

    messages = [{"role": "user", "content": "test"}]
    result = await chat_json(messages)

    assert result == '{"key": "value"}'
    mock_client.chat.completions.create.assert_awaited_once_with(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.3,
        max_tokens=256,
        response_format={"type": "json_object"},
    )


@pytest.mark.asyncio
@patch("mustachar.infra.groq_client._get_client")
async def test_chat_json_returns_empty_on_none_content(mock_get: AsyncMock) -> None:
    mock_message = MagicMock()
    mock_message.content = None
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get.return_value = mock_client

    result = await chat_json([{"role": "user", "content": "test"}])

    assert result == ""
