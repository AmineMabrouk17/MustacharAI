"""ChromaDB client wrapper for vector storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import chromadb
import numpy as np
import structlog
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

if TYPE_CHECKING:
    from chromadb.api.types import Documents, Embeddings

from mustachar.core.settings import settings

logger = structlog.get_logger()

EMBEDDING_MODEL = "intfloat/multilingual-e5-small"

QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


class E5PrefixEmbeddingFunction(SentenceTransformerEmbeddingFunction):
    """multilingual-e5-small with the canonical e5 query/passage prefixes.

    e5 models are trained on asymmetric ``query:``/``passage:`` text pairs, so
    retrieval quality degrades when both sides are embedded bare. ChromaDB asks
    document embedding via ``__call__`` and query embedding via ``embed_query``;
    this wrapper routes each through its required prefix.
    """

    def _encode(self, texts: Documents) -> Embeddings:
        return [
            np.array(vector, dtype=np.float32)
            for vector in self._model.encode(
                list(texts),
                convert_to_numpy=True,
                normalize_embeddings=self.normalize_embeddings,
            )
        ]

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002
        return self._encode([PASSAGE_PREFIX + text for text in input])

    def embed_query(self, input: Documents) -> Embeddings:  # noqa: A002
        return self._encode([QUERY_PREFIX + text for text in input])


def _get_embedding_function() -> E5PrefixEmbeddingFunction:
    """Return the multilingual-e5-small embedding function with e5 prefixes."""
    return E5PrefixEmbeddingFunction(model_name=EMBEDDING_MODEL)


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
        metadata={"hnsw:space": "cosine"},
    )
