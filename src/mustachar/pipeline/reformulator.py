"""Query reformulation pipeline stage: Darja → MSA legal search terms."""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from mustachar.infra.groq_client import chat_json

logger = structlog.get_logger()

SYSTEM_PROMPT = """\
You are a legal search query translator. Your task is to rewrite a question \
in Tunisian Darja into a French legal search query (the Tunisian legal corpus \
is indexed in French).

Return ONLY a JSON object:
{
  "primary_query": "French legal search query",
  "keywords": ["mot1", "mot2", "mot3"]
}

Rules:
1. primary_query: one concise sentence in French legal terminology.
2. keywords: 2-5 French legal keywords.
3. Do NOT use Darja or Arabic in the output.
4. Do NOT add any text outside the JSON.
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
        raw = await chat_json(messages, max_tokens=120)
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
