"""ChromaDB client wrapper for vector storage."""

from __future__ import annotations

from typing import Any

import chromadb
import structlog

from mustachar.core.settings import settings

logger = structlog.get_logger()


def get_chroma_client() -> Any:
    """Return a persistent ChromaDB client."""
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def get_or_create_collection(
    client: Any,
    name: str = "legal_corpus",
) -> Any:
    """Get or create a ChromaDB collection."""
    return client.get_or_create_collection(name=name)
