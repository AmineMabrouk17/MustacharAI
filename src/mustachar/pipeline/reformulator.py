"""Query reformulation pipeline stage: Darja → MSA legal search terms."""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from mustachar.infra.groq_client import chat_json

logger = structlog.get_logger()

SYSTEM_PROMPT = """\
أنت مترجم للغة العربية الفصحى. مهمتك إعادة صياغة سؤال بالدارجة التونسية \
إلى استعلام بحث قانوني بالعربية الفصحى.

أعد النتيجة بصيغة JSON فقط:
{
  "primary_query": "الاستعلام الرئيسي بالعربية الفصحى",
  "keywords": ["كلمة1", "كلمة2", "كلمة3"]
}

قواعد:
1. primary_query: جملة واحدة واضحة ومختصرة بالعربية الفصحى ( Legal MSA).
2. keywords: 2-5 كلمات مفتاحية قانونية بالعربية الفصحى.
3. لا تستخدم الدارجة في الإخراج.
4. لا تُضف شرحًا أو نصًا خارج JSON.
"""

FALLBACK_RESULT: dict[str, Any] = {
    "primary_query": "",
    "keywords": [],
}


async def reformulate(darja_query: str) -> dict[str, Any]:
    """Reformulate a Darja query into MSA legal search terms.

    Returns a dict with:
      - ``primary_query``: the MSA search string
      - ``keywords``: list of legal keywords
      - ``latency_ms``: wall-clock latency
    """
    start = time.perf_counter()

    if not darja_query.strip():
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "reformulator_empty_query",
            latency_ms=round(elapsed_ms, 1),
        )
        return {**FALLBACK_RESULT, "latency_ms": round(elapsed_ms, 1)}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": darja_query},
    ]

    try:
        raw = await chat_json(messages, max_tokens=35)
        result: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        logger.exception("reformulator_parse_error", query=darja_query)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {**FALLBACK_RESULT, "latency_ms": round(elapsed_ms, 1)}

    primary = result.get("primary_query", "")
    keywords = result.get("keywords", [])

    if not isinstance(keywords, list):
        keywords = []

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "reformulator_completed",
        query_length=len(darja_query),
        primary_length=len(primary),
        keywords_count=len(keywords),
        latency_ms=round(elapsed_ms, 1),
    )

    return {
        "primary_query": primary,
        "keywords": keywords,
        "latency_ms": round(elapsed_ms, 1),
    }
