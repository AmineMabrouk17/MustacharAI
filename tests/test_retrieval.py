"""Tests for the retrieval pipeline stage."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from mustachar.pipeline.retrieval import RETRIEVAL_THRESHOLD, retrieve


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
def test_retrieve_returns_hits_below_threshold(
    mock_client_fn: MagicMock,
    mock_collection_fn: MagicMock,
) -> None:
    collection = MagicMock()
    collection.query.return_value = _mock_query_result(
        documents=["نص القانون"],
        metadatas=[{"source": "majalla1.pdf", "article": "المادة 1", "category": ""}],
        distances=[0.4],
    )
    mock_collection_fn.return_value = collection

    hits = retrieve("سؤال")

    assert len(hits) == 1
    assert hits[0]["content"] == "نص القانون"
    assert hits[0]["source"] == "majalla1.pdf"
    assert hits[0]["article"] == "المادة 1"
    assert hits[0]["distance"] == 0.4


@patch("mustachar.pipeline.retrieval.get_or_create_collection")
@patch("mustachar.pipeline.retrieval.get_chroma_client")
def test_retrieve_filters_above_threshold(
    mock_client_fn: MagicMock,
    mock_collection_fn: MagicMock,
) -> None:
    collection = MagicMock()
    collection.query.return_value = _mock_query_result(
        documents=["نص قريب", "نص بعيد"],
        metadatas=[
            {"source": "a.pdf", "article": "المادة 1", "category": ""},
            {"source": "b.pdf", "article": "المادة 2", "category": ""},
        ],
        distances=[0.5, 0.9],
    )
    mock_collection_fn.return_value = collection

    hits = retrieve("سؤال")

    assert len(hits) == 1
    assert hits[0]["distance"] == 0.5


@patch("mustachar.pipeline.retrieval.get_or_create_collection")
@patch("mustachar.pipeline.retrieval.get_chroma_client")
def test_retrieve_returns_empty_when_all_above_threshold(
    mock_client_fn: MagicMock,
    mock_collection_fn: MagicMock,
) -> None:
    collection = MagicMock()
    collection.query.return_value = _mock_query_result(
        documents=["نص بعيد جداً"],
        metadatas=[{"source": "x.pdf", "article": "المادة 5", "category": ""}],
        distances=[0.95],
    )
    mock_collection_fn.return_value = collection

    hits = retrieve("سؤال")

    assert hits == []


@patch("mustachar.pipeline.retrieval.get_or_create_collection")
@patch("mustachar.pipeline.retrieval.get_chroma_client")
def test_retrieve_custom_threshold(
    mock_client_fn: MagicMock,
    mock_collection_fn: MagicMock,
) -> None:
    collection = MagicMock()
    collection.query.return_value = _mock_query_result(
        documents=["نص"],
        metadatas=[{"source": "a.pdf", "article": "المادة 1", "category": ""}],
        distances=[0.6],
    )
    mock_collection_fn.return_value = collection

    hits = retrieve("سؤال", threshold=0.5)

    assert hits == []


def test_default_threshold_value() -> None:
    assert RETRIEVAL_THRESHOLD == 0.65
