"""Tests for ChromaDB client wrapper."""

from __future__ import annotations

from mustachar.infra.chroma_client import get_chroma_client, get_or_create_collection


def test_get_chroma_client_returns_client() -> None:
    client = get_chroma_client()
    assert client is not None


def test_get_or_create_collection() -> None:
    client = get_chroma_client()
    collection = get_or_create_collection(client, name="test_collection_pytest")
    assert collection is not None
    assert collection.name == "test_collection_pytest"
    client.delete_collection("test_collection_pytest")
