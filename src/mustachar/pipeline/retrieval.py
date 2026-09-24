"""Retrieval pipeline stage: dense vector search over the legal corpus."""

from __future__ import annotations

import re
import time
from typing import Any

import structlog

from mustachar.core.settings import settings
from mustachar.infra.chroma_client import get_chroma_client, get_or_create_collection

logger = structlog.get_logger()

DEFAULT_N_RESULTS = 5

# Arabic stopwords dropped when deriving lexical boost terms from the query
ARABIC_STOPWORDS = {
    "شنوة", "شنو", "واش", "على", "في", "من", "إلى", "عن", "مع", "ما", "هي",
    "هو", "هل", "ليش", "كيف", "متى", "أين", "التي", "الذي", "هذه", "هذا",
    "أن", "إن", "لا", "ثم", "أو", "كل", "بين", "عند", "سؤال", "سؤالي",
}

LEXICAL_BONUS = 0.08  # distance discount when a *distinctive* term appears

# Per-process cache of corpus term frequency (counts chunks containing a term)
_CORPUS_COUNTS: dict[str, int] = {}
_CORPUS_TOTAL: int | None = None


def _corpus_frequency(collection: Any, term: str) -> int:
    """Number of chunks whose content contains *term* (cached per process)."""
    if term not in _CORPUS_COUNTS:
        try:
            hits = collection.get(
                where_document={"$contains": term}, include=["metadatas"]
            )
            _CORPUS_COUNTS[term] = len(hits.get("ids", []))
        except Exception:
            _CORPUS_COUNTS[term] = -1
    return _CORPUS_COUNTS[term]


def extract_ar_keywords(texts: list[str]) -> list[str]:
    """Distinctive Arabic words (>=3 chars, not stopwords) across query texts.

    Harvests terms from the raw question *and* the Arabic MSA reformulation so
    legal vocabulary such as «إنشاء» or «الذكاء» survives into the keyword
    recall and IDF-boost passes despite dialect filler words.
    """
    words: list[str] = []
    seen: set[str] = set()
    for t in texts:
        for w in re.findall(r"[\u0621-\u064A]{3,}", t):
            if w not in ARABIC_STOPWORDS and w not in seen:
                words.append(w)
                seen.add(w)
    return words[:10]


def _lexical_boost(terms: list[str], content: str) -> float:
    if not terms:
        return 0.0
    return LEXICAL_BONUS if any(t in content for t in terms) else 0.0


def retrieve(
    query: str,
    *,
    queries: list[str] | None = None,
    n_results: int = DEFAULT_N_RESULTS,
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Query ChromaDB for the most relevant legal articles.

    *query* is the primary search text; *queries* may carry additional
    search variants (e.g. the original Arabic question alongside the
    reformulated French query). Results from all queries are merged by
    Chroma ID, keeping the best (lowest) distance per chunk, then filtered
    by threshold and returned best-first.

    Returns a list of dicts with keys ``content``, ``source``,
    ``article``, ``category``, and ``distance``.  Results whose cosine
    similarity is below *threshold* (defaulting to
    ``settings.retrieval_threshold``) are discarded.
    """
    start = time.perf_counter()

    client = get_chroma_client()
    collection = get_or_create_collection(client)

    all_queries = [query] + [q for q in (queries or []) if q and q != query]
    results = collection.query(
        query_texts=all_queries,
        n_results=max(n_results * 3, 9),
        include=["documents", "metadatas", "distances"],
    )

    lexical_terms = extract_ar_keywords(all_queries)

    best: dict[str, dict[str, Any]] = {}  # chroma id -> best hit
    for qi, _ in enumerate(all_queries):
        documents: list[str] = results.get("documents", [[]])[qi]
        metadatas: list[dict[str, Any]] = results.get("metadatas", [[]])[qi]
        distances: list[float] = results.get("distances", [[]])[qi]
        ids: list[str] = results.get("ids", [[]])[qi]
        for doc, meta, dist, chunk_id in zip(
            documents, metadatas, distances, ids, strict=True
        ):
            hit = {
                "content": doc,
                "source": meta.get("source", ""),
                "article": meta.get("article", ""),
                "category": meta.get("category", ""),
                "distance": dist,
            }
            prev = best.get(chunk_id)
            if prev is None or dist < prev["distance"]:
                best[chunk_id] = hit

    # Keyword-recall pass: dense retrieval misses relevant chunks on noisy OCR,
    # so also pull the nearest chunks that literally contain an Arabic query
    # term (e.g. "السرقة") — these enter the pool with real distances.
    for kw in [t for t in lexical_terms if len(t) >= 4][:4]:
        try:
            kw_res = collection.query(
                query_texts=all_queries,
                n_results=max(n_results * 2, 6),
                where_document={"$contains": kw},
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            continue  # keyword pass is best-effort
        for qi, _ in enumerate(all_queries):
            documents = kw_res.get("documents", [[]])[qi]
            metadatas = kw_res.get("metadatas", [[]])[qi]
            distances = kw_res.get("distances", [[]])[qi]
            ids = kw_res.get("ids", [[]])[qi]
            for doc, meta, dist, chunk_id in zip(
                documents, metadatas, distances, ids, strict=True
            ):
                hit = {
                    "content": doc,
                    "source": meta.get("source", ""),
                    "article": meta.get("article", ""),
                    "category": meta.get("category", ""),
                    "distance": dist,
                }
                prev = best.get(chunk_id)
                if prev is None or dist < prev["distance"]:
                    best[chunk_id] = hit

    # A term only earns the lexical priority bonus if it is rare across the
    # whole corpus (<1.1%, floor 15 chunks): generic legal vocabulary such as
    # "القانون" or "العقوبة" appears in dozens/hundreds of chunks and would
    # otherwise apply the bonus to every hit, defeating the re-ranking.
    global _CORPUS_TOTAL
    if _CORPUS_TOTAL is None:
        _CORPUS_TOTAL = collection.count()
    rare_limit = max(15, int(_CORPUS_TOTAL * 0.011))
    boost_terms = [
        t
        for t in lexical_terms
        if 0 <= _corpus_frequency(collection, t) <= rare_limit
    ]

    hits = sorted(
        best.values(),
        key=lambda h: h["distance"] - _lexical_boost(boost_terms, h["content"]),
    )

    max_distance = 1.0 - (
        settings.retrieval_threshold if threshold is None else threshold
    )
    hits = [h for h in hits if h["distance"] <= max_distance][:n_results]

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "retrieval_completed",
        query_length=len(query),
        queries=len(all_queries),
        hits=len(hits),
        latency_ms=round(elapsed_ms, 1),
    )
    return hits
