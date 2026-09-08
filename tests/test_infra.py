"""Tests for infrastructure clients (Groq, Edge-TTS, ChromaDB)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mustachar.core.settings import Settings
from mustachar.infra.groq_client import chat, transcribe

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ── Settings ────────────────────────────────────────────────────


def test_settings_defaults() -> None:
    s = Settings()
    assert s.app_name == "MustacharAI"
    assert s.debug is False


# ── Groq client ─────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("mustachar.infra.groq_client._get_client")
async def test_chat_returns_response(mock_get: AsyncMock) -> None:
    mock_msg = MagicMock()
    mock_msg.content = "القانون ينص على ذلك"
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_resp
    mock_get.return_value = mock_client

    result = await chat([{"role": "user", "content": "ما هو القانون؟"}])
    assert result == "القانون ينص على ذلك"


@pytest.mark.asyncio
@patch("mustachar.infra.groq_client._get_client")
async def test_transcribe_returns_text(mock_get: AsyncMock) -> None:
    mock_resp = AsyncMock()
    mock_resp.text = "مرحبا"
    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create.return_value = mock_resp
    mock_get.return_value = mock_client

    result = await transcribe(audio=("test.webm", b"fake-audio"))
    assert result == "مرحبا"
    settings = Settings()
    mock_client.audio.transcriptions.create.assert_awaited_with(
        model=settings.groq_stt_model,
        file=("test.webm", b"fake-audio"),
        language="ar",
    )


# ── Edge-TTS client ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tts_stage_yields_chunks() -> None:
    async def _fake_stream() -> AsyncIterator[dict[str, Any]]:
        chunks: list[dict[str, Any]] = [
            {"type": "audio", "data": b"chunk1"},
            {"type": "WordBoundary", "data": {}},
            {"type": "audio", "data": b"chunk2"},
        ]
        for chunk in chunks:
            yield chunk

    mock_comm = MagicMock()
    mock_comm.stream = _fake_stream

    with patch(
        "mustachar.infra.edge_tts_client.edge_tts.Communicate", return_value=mock_comm
    ):
        from mustachar.pipeline.tts import tts_stage

        result: list[bytes] = []
        async for chunk in tts_stage("ahlan"):
            result.append(chunk)

    assert result == [b"chunk1", b"chunk2"]


# ── ChromaDB client ─────────────────────────────────────────────


def test_collection_uses_cosine_space() -> None:
    from mustachar.infra.chroma_client import get_or_create_collection

    client = MagicMock()
    get_or_create_collection(client)
    client.get_or_create_collection.assert_called_once()
    _, kwargs = client.get_or_create_collection.call_args
    assert kwargs["metadata"] == {"hnsw:space": "cosine"}


def test_collection_uses_e5_small_embedding_function() -> None:
    from mustachar.infra import chroma_client

    with patch(
        "mustachar.infra.chroma_client.E5PrefixEmbeddingFunction",
        return_value=MagicMock(),
    ) as mock_embed:
        embedding_fn = chroma_client._get_embedding_function()

    mock_embed.assert_called_once_with(model_name=chroma_client.EMBEDDING_MODEL)
    assert embedding_fn is mock_embed.return_value


def test_e5_prefixes_query_and_passage() -> None:
    import numpy as np
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    from mustachar.infra import chroma_client

    model = MagicMock()
    model.encode.return_value = np.zeros((2, 8))

    with patch.object(
        SentenceTransformerEmbeddingFunction,
        "models",
        {chroma_client.EMBEDDING_MODEL: model},
    ):
        ef = chroma_client.E5PrefixEmbeddingFunction(
            model_name=chroma_client.EMBEDDING_MODEL,
        )

    ef(["العقد اتفاق", "المحكمة"])
    assert model.encode.call_count == 1
    assert model.encode.call_args.args[0] == [
        chroma_client.PASSAGE_PREFIX + "العقد اتفاق",
        chroma_client.PASSAGE_PREFIX + "المحكمة",
    ]

    model.encode.return_value = np.zeros((1, 8))
    ef.embed_query(["نص العقد"])
    assert model.encode.call_count == 2
    assert model.encode.call_args.args[0] == [chroma_client.QUERY_PREFIX + "نص العقد"]


# ── CLI index ───────────────────────────────────────────────────


def test_collect_pdfs_single_file(tmp_path: Any) -> None:
    from mustachar.cli.index import _collect_pdfs

    pdf = tmp_path / "law.pdf"
    pdf.write_text("fake")
    assert _collect_pdfs(str(pdf), None) == [pdf]


def test_collect_pdfs_no_input() -> None:
    from mustachar.cli.index import _collect_pdfs

    with pytest.raises(SystemExit):
        _collect_pdfs(None, None)


def test_build_parser() -> None:
    from mustachar.cli.index import build_parser

    parser = build_parser()
    args = parser.parse_args(["--file", "test.pdf"])
    assert args.file == "test.pdf"
    assert args.dry_run is False


def test_load_manifest(tmp_path: Any) -> None:
    from mustachar.cli.index import _load_manifest

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "filename,category\n"
        "a.pdf,قانون التجارة\n"
        "b.pdf,القانون الجنائي\n",
        encoding="utf-8",
    )
    assert _load_manifest(str(manifest)) == {
        "a.pdf": "قانون التجارة",
        "b.pdf": "القانون الجنائي",
    }
