"""Query reformulation pipeline stage: Darja → French + Arabic MSA legal queries."""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from mustachar.infra.llm_client import chat_json

logger = structlog.get_logger()

SYSTEM_PROMPT = """\
You are a legal search query translator for Tunisia. A question in Tunisian \
Darja must be rewritten into TWO legal search queries — one in French and one \
in Modern Standard Arabic (MSA) — because the Tunisian legal corpus is indexed \
in Arabic.

Return ONLY a JSON object:
{
  "primary_query": "French legal search query",
  "keywords": ["mot1", "mot2", "mot3"],
  "arabic_query": "Arabic MSA legal search query",
  "arabic_keywords": ["كلمة1", "كلمة2", "كلمة3"]
}

Rules:
1. primary_query: one concise sentence in French legal terminology.
2. keywords: 2-5 French legal keywords.
3. arabic_query: one concise sentence in Modern Standard Arabic legal \
terminology (formal الفصحى, NEVER Darja).
4. arabic_keywords: 2-5 Arabic legal keywords in formal MSA.
5. Do NOT add any text outside the JSON.
"""

FALLBACK_RESULT: dict[str, Any] = {
    "primary_query": "",
    "keywords": [],
    "arabic_query": "",
    "arabic_keywords": [],
}


async def reformulate(darja_query: str) -> dict[str, Any]:
    """Reformulate a Darja query into French + Arabic MSA legal search terms.

    Returns a dict with:
      - ``primary_query``: the French search string
      - ``keywords``: list of French legal keywords
      - ``arabic_query``: the Arabic MSA legal search string
      - ``arabic_keywords``: list of Arabic legal keywords
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
        raw = await chat_json(messages, max_tokens=600)
        result: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        logger.exception("reformulator_parse_error", query=darja_query)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {**FALLBACK_RESULT, "latency_ms": round(elapsed_ms, 1)}

    primary = result.get("primary_query", "")
    keywords = result.get("keywords", [])
    arabic_query = result.get("arabic_query", "")
    arabic_keywords = result.get("arabic_keywords", [])

    if not isinstance(keywords, list):
        keywords = []
    if not isinstance(arabic_keywords, list):
        arabic_keywords = []

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "reformulator_completed",
        query_length=len(darja_query),
        primary_length=len(primary),
        keywords_count=len(keywords),
        arabic_query_length=len(arabic_query),
        arabic_keywords_count=len(arabic_keywords),
        latency_ms=round(elapsed_ms, 1),
    )

    return {
        "primary_query": primary,
        "keywords": keywords,
        "arabic_query": arabic_query,
        "arabic_keywords": arabic_keywords,
        "latency_ms": round(elapsed_ms, 1),
    }
