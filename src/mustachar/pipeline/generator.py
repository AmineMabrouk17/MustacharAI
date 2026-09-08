"""Grounded reasoning pipeline stage: French RAG generation with zero-hallucination prompt."""

from __future__ import annotations

import time
from typing import Any

import structlog

from mustachar.infra.groq_client import chat
from mustachar.pipeline.retrieval import DEFAULT_N_RESULTS, retrieve

logger = structlog.get_logger()

FALLBACK_FRENCH = (
    "Je n'ai pas trouvé d'informations suffisantes dans le corpus juridique pour "
    "répondre à cette question. Reformulez votre demande ou consultez un avocat pour "
    "une réponse plus précise."
)

SYSTEM_PROMPT = """\
Vous êtes un conseiller juridique tunisien. Votre rôle est de répondre aux \
questions de l'utilisateur en vous appuyant exclusivement sur les textes \
juridiques fournis dans le contexte.

Règles strictes :
1. Utilisez uniquement les informations du contexte. N'inventez jamais une \
information absente du contexte.
2. Toute réponse affirmative doit obligatoirement citer le Fasl (article) et \
la Majalla (code) utilisés, tels qu'ils figurent dans le contexte.
3. Répondez en français, de manière concise et directe, en prose claire.
4. Si le contexte ne contient aucune réponse claire, répondez : "Je n'ai pas \
trouvé d'informations suffisantes dans le corpus juridique pour répondre à \
cette question."
5. Restez bref : quelques phrases courtes, sans préambule ni conclusion inutile.
"""


def _build_context_block(hits: list[dict[str, Any]]) -> str:
    """Format retrieval hits into a numbered context block for the prompt."""
    parts: list[str] = []
    for i, hit in enumerate(hits, 1):
        source = hit.get("source", "")
        article = hit.get("article", "")
        content = hit.get("content", "")
        parts.append(f"[{i}] Source: {source} | {article}\n{content}")
    return "\n\n".join(parts)


async def generate(
    query: str,
    *,
    n_results: int = DEFAULT_N_RESULTS,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Run retrieval then grounded generation.

    Returns a dict with:
      - ``answer``: the generated French response
      - ``hits``: the retrieval results used
      - ``fallback``: whether the fallback message was returned
      - ``latency_ms``: total latency for retrieval + generation
    """
    start = time.perf_counter()

    hits = retrieve(query, n_results=n_results, threshold=threshold)

    if not hits:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "generator_fallback",
            query_length=len(query),
            latency_ms=round(elapsed_ms, 1),
        )
        return {
            "answer": FALLBACK_FRENCH,
            "hits": hits,
            "fallback": True,
            "latency_ms": round(elapsed_ms, 1),
        }

    context_block = _build_context_block(hits)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Contexte juridique :\n\n{context_block}\n\nQuestion de "
                f"l'utilisateur :\n{query}"
            ),
        },
    ]

    answer = await chat(messages)

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "generator_completed",
        query_length=len(query),
        hits_used=len(hits),
        answer_length=len(answer),
        latency_ms=round(elapsed_ms, 1),
    )
    return {
        "answer": answer,
        "hits": hits,
        "fallback": False,
        "latency_ms": round(elapsed_ms, 1),
    }
