"""ChromaDB client wrapper for vector storage."""

from __future__ import annotations

from typing import Any

import chromadb
import structlog
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from mustachar.core.settings import settings

logger = structlog.get_logger()

EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


def _get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    """Return the multilingual-e5-small embedding function."""
    return SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)


def get_chroma_client() -> Any:
    """Return a persistent ChromaDB client."""
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def get_or_create_collection(
    client: Any,
    name: str = "legal_corpus",
) -> Any:
    """Get or create a ChromaDB collection with multilingual embeddings."""
    return client.get_or_create_collection(
        name=name,
        embedding_function=_get_embedding_function(),
    )
