"""Retrieval pipeline stage: dense vector search over the legal corpus."""

from __future__ import annotations

import time
from typing import Any

import structlog

from mustachar.infra.chroma_client import get_chroma_client, get_or_create_collection

logger = structlog.get_logger()

RETRIEVAL_THRESHOLD = 0.65


def retrieve(
    query: str,
    *,
    n_results: int = 5,
    threshold: float = RETRIEVAL_THRESHOLD,
) -> list[dict[str, Any]]:
    """Query ChromaDB for the most relevant legal articles.

    Returns a list of dicts with keys ``content``, ``source``,
    ``article``, ``category``, and ``distance``.  Results below
    *threshold* distance are discarded.
    """
    start = time.perf_counter()

    client = get_chroma_client()
    collection = get_or_create_collection(client)

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    hits: list[dict[str, Any]] = []
    documents: list[str] = results.get("documents", [[]])[0]
    metadatas: list[dict[str, Any]] = results.get("metadatas", [[]])[0]
    distances: list[float] = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(documents, metadatas, distances, strict=True):
        if dist <= threshold:
            hits.append(
                {
                    "content": doc,
                    "source": meta.get("source", ""),
                    "article": meta.get("article", ""),
                    "category": meta.get("category", ""),
                    "distance": dist,
                }
            )

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "retrieval_completed",
        query_length=len(query),
        hits=len(hits),
        latency_ms=round(elapsed_ms, 1),
    )
    return hits
