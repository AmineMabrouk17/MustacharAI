"""ChromaDB client wrapper for vector storage."""

from __future__ import annotations

import chromadb
import structlog

from mustachar.core.settings import settings

logger = structlog.get_logger()


def get_chroma_client() -> chromadb.ClientAPI:
    """Return a persistent ChromaDB client."""
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def get_or_create_collection(
    client: chromadb.ClientAPI,
    name: str = "legal_corpus",
) -> chromadb.Collection:
    """Get or create a ChromaDB collection."""
    return client.get_or_create_collection(name=name)
