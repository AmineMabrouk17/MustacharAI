"""Grounded reasoning pipeline stage: language-aware RAG generation with zero-hallucination prompt."""

from __future__ import annotations

import time
from typing import Any

import structlog

from mustachar.infra.llm_client import chat
from mustachar.pipeline.retrieval import DEFAULT_N_RESULTS, retrieve

logger = structlog.get_logger()

FALLBACK_FRENCH = (
    "Je n'ai pas trouvé d'informations suffisantes dans le corpus juridique pour "
    "répondre à cette question. Reformulez votre demande ou consultez un avocat pour "
    "une réponse plus précise."
)

FALLBACK_ARABIC = (
    "لم أتمكن من العثور على معلومات كافية في النصوص القانونية المتوفرة للإجابة على "
    "هذا السؤال. يرجى إعادة صياغة الطلب أو استشارة محامٍ للحصول على إجابة أدق."
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

SYSTEM_PROMPT_AR = """\
Vous êtes un conseiller juridique tunisien. Votre rôle est de répondre aux \
questions de l'utilisateur en vous appuyant exclusivement sur les textes \
juridiques fournis dans le contexte.

Règles strictes :
1. Utilisez uniquement les informations du contexte. N'inventez jamais une \
information absente du contexte.
2. Toute réponse affirmative doit obligatoirement citer le Fasl (الفصل) et la \
Majalla (المجلة) utilisés, avec leurs numéros exacts tels qu'ils figurent dans \
le contexte.
3. Répondez en arabe moderne standard (الفصحى), de manière concise et directe, \
en prose claire.
4. Si le contexte ne contient aucune réponse claire, répondez : "لم أتمكن من \
العثور على معلومات كافية في النصوص القانونية المتوفرة للإجابة على هذا السؤال."
5. Restez bref : quelques phrases courtes, sans préambule ni conclusion inutile.
"""


def _has_arabic(text: str) -> bool:
    """True if *text* contains Arabic script characters."""
    return any("\u0600" <= ch <= "\u06FF" for ch in text)


def fallback_for(question: str) -> str:
    """Language-appropriate fallback message (Arabic for Arabic questions)."""
    return FALLBACK_ARABIC if _has_arabic(question) else FALLBACK_FRENCH


def _build_context_block(hits: list[dict[str, Any]]) -> str:
    """Format retrieval hits into a numbered context block for the prompt.

    Chunk/context sizes are capped so the prompt always fits the free-tier
    input-token budget even if a stray oversized chunk (OCR merge, preamble)
    gets retrieved.
    """
    MAX_CONTENT_CHARS = 2000  # per hit
    MAX_CONTEXT_CHARS = 6000  # total block
    parts: list[str] = []
    for i, hit in enumerate(hits, 1):
        source = hit.get("source", "")
        article = hit.get("article", "")
        content = hit.get("content", "")
        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS] + "…"
        parts.append(f"[{i}] Source: {source} | {article}\n{content}")
    block = "\n\n".join(parts)
    if len(block) > MAX_CONTEXT_CHARS:
        block = block[:MAX_CONTEXT_CHARS] + "…"
    return block


async def generate(
    query: str,
    *,
    n_results: int = DEFAULT_N_RESULTS,
    threshold: float | None = None,
    extra_queries: list[str] | None = None,
    language_question: str | None = None,
) -> dict[str, Any]:
    """Run retrieval then grounded generation.

    *language_question* is the user's original question, used to pick the
    answer language (and fallback message).  When omitted, the first
    ``extra_queries`` entry (or *query*) is used instead — extra_queries may
    carry Arabic MSA reformulations, so passing the raw question explicitly
    keeps French questions answered in French.

    Returns a dict with:
      - ``answer``: the generated response (French or Arabic, following the
        language of the user's question)
      - ``hits``: the retrieval results used
      - ``fallback``: whether the fallback message was returned
      - ``latency_ms``: total latency for retrieval + generation
    """
    start = time.perf_counter()

    hits = retrieve(
        query,
        queries=extra_queries,
        n_results=n_results,
        threshold=threshold,
    )

    source_question = language_question or (extra_queries or [query])[0]

    if not hits:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "generator_fallback",
            query_length=len(query),
            latency_ms=round(elapsed_ms, 1),
        )
        return {
            "answer": fallback_for(source_question),
            "hits": hits,
            "fallback": True,
            "latency_ms": round(elapsed_ms, 1),
        }

    context_block = _build_context_block(hits)

    system_prompt = (
        SYSTEM_PROMPT_AR if _has_arabic(source_question) else SYSTEM_PROMPT
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Contexte juridique :\n\n{context_block}\n\nQuestion de "
                f"l'utilisateur :\n{source_question}"
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
