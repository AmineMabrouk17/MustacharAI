"""Grounded reasoning pipeline stage: RAG generation with zero-hallucination prompt."""

from __future__ import annotations

import time
from typing import Any

import structlog

from mustachar.infra.groq_client import chat
from mustachar.pipeline.retrieval import RETRIEVAL_THRESHOLD, retrieve

logger = structlog.get_logger()

FALLBACK_DARJA = (
    "ما لقيتش معلومات كافية في القانون على هالسؤال. حلّي تسأل محامي باش يعطيك إجابة أدق."
)

SYSTEM_PROMPT = """\
أنت مستشار قانوني تونسي ذكي. مهمتك الإجابة على أسئلة المستخدم بناءً \
الكلي على النصوص القانونية المقدّمة في السياق فقط.

قواعد صارمة:
1. استخدم فقط المعلومات الموجودة في السياق. لا تختلق أو ت倒在 أي معلومة خارج السياق.
2. عند الإجابة، اذكر دائماً الفصل (Fasl) والمجلة (Majalla) المستخدمة.
3. الجواب لازم يكون بالدارجة التونسية مكتوبة بالحروف العربية.
4. إذا السياق ما فيهش إجابة واضحة، قول "ما لقيتش إجابة واضحة في القانون على هالسؤال".
5. لا تكتب بالفرنسية أو الإنجليزية في الجواب.
6. كن مختصراً ومباشرًا في الإجابة.
"""


def _build_context_block(hits: list[dict[str, Any]]) -> str:
    """Format retrieval hits into a numbered context block for the prompt."""
    parts: list[str] = []
    for i, hit in enumerate(hits, 1):
        source = hit.get("source", "")
        article = hit.get("article", "")
        content = hit.get("content", "")
        parts.append(f"[{i}] المصدر: {source} | {article}\n{content}")
    return "\n\n".join(parts)


async def generate(
    query: str,
    *,
    n_results: int = 5,
    threshold: float = RETRIEVAL_THRESHOLD,
) -> dict[str, Any]:
    """Run retrieval then grounded generation.

    Returns a dict with:
      - ``answer``: the generated Darja response
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
            "answer": FALLBACK_DARJA,
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
                f"السياق القانوني:\n\n{context_block}\n\nسؤال المستخدم:\n{query}"
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
