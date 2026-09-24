"""Text RAG pipeline orchestrator: Reformulate → Retrieve → Generate."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from mustachar.infra.llm_client import get_active_model
from mustachar.pipeline.generator import fallback_for, generate
from mustachar.pipeline.reformulator import reformulate

logger = structlog.get_logger()


def _format_llm_error(exc: Exception) -> tuple[str, str]:
    """Build a user-facing Arabic error message plus the raw technical detail.

    Returns ``(answer_text, detail)`` where ``detail`` is a single-line,
    truncated version of the underlying exception.  Gemini error JSON is
    collapsed to ``Gemini HTTP <code>: <message>`` for readability.
    """
    active = get_active_model()
    detail = " ".join(str(exc).split())[:250]
    if detail.startswith("Gemini HTTP"):
        detail = _clean_gemini_error(str(exc)) or detail
    prefix = f"نموذج {active['provider']}/{active['model']}"
    if detail:
        answer = f"⚠️ تعذّر الحصول على رد من {prefix}. تفاصيل الخطأ: {detail}"
    else:
        answer = f"⚠️ تعذّر الحصول على رد من {prefix}. حاول مرة أخرى أو بدّل النموذج."
    return answer, detail


def _clean_gemini_error(text: str) -> str:
    """Extract ``Gemini HTTP <code>: <message>`` from the Gemini error JSON."""
    try:
        import json as _json
        import re

        m = re.search(r"Gemini HTTP (\d+)", text)
        if not m:
            return ""
        code = m.group(1)
        payload = text[text.index(":"):].strip()
        payload = payload.lstrip(": ").strip()
        if payload.startswith("{"):
            data = _json.loads(payload)
            message = data.get("error", {}).get("message", "")
            if message:
                return f"Gemini HTTP {code}: {' '.join(message.split())[:220]}"
    except Exception:
        pass
    return ""


@dataclass
class PipelineResult:
    """Full pipeline result with per-stage latency tracking."""

    question: str = ""
    reformulated_query: str = ""
    answer: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    fallback: bool = True
    error: str = ""
    stage_latencies_ms: dict[str, float] = field(default_factory=dict)
    total_latency_ms: float = 0.0


async def run_pipeline(question: str) -> PipelineResult:
    """Execute the text-only RAG pipeline: Reformulate → Retrieve → Generate.

    Returns the grounded French answer plus retrieved legal citations. The query
    is first translated from Darja into a French legal search query, then used to
    retrieve from the corpus before generation. A generation failure returns the
    French fallback message.
    """
    pipeline_start = time.perf_counter()
    result = PipelineResult(question=question)

    # ── Stage 1: Reformulate ─────────────────────────────────────
    stage_start = time.perf_counter()
    try:
        reformulated = await reformulate(question)
    except Exception:
        logger.exception("pipeline.reformulate_error")
        result.reformulated_query = ""
        result.stage_latencies_ms["reformulate"] = round(
            (time.perf_counter() - stage_start) * 1000, 1
        )
    else:
        result.reformulated_query = reformulated.get("primary_query", "")
        result.stage_latencies_ms["reformulate"] = reformulated.get("latency_ms", 0.0)

    search_query = result.reformulated_query or question

    # ── Stage 2 + 3: Retrieve + Generate ─────────────────────────
    # Retrieve with the reformulated (French) query plus Arabic-leg queries:
    # the Arabic MSA reformulation first (cleanest lexical signal, prioritised
    # by the keyword extractor), then the raw question — the cross-lingual
    # reformulation alone misses specific legal terms, while the MSA/raw Arabic
    # legs match the Arabic corpus directly.
    extra_queries: list[str] = []
    arabic_query = reformulated.get("arabic_query", "")
    for q in (arabic_query, question):
        if q and q.strip() and q != search_query and q not in extra_queries:
            extra_queries.append(q)
    stage_start = time.perf_counter()
    try:
        gen_result = await generate(
            search_query,
            extra_queries=extra_queries or None,
            language_question=question,
        )
    except Exception as exc:
        logger.exception("pipeline.generate_error")
        result.answer, result.error = _format_llm_error(exc)
        result.fallback = True
        result.citations = []
    else:
        result.answer = gen_result.get("answer", fallback_for(question))
        result.fallback = gen_result.get("fallback", True)
        result.citations = [
            {
                "source": hit.get("source", ""),
                "article": hit.get("article", ""),
                "content": hit.get("content", "")[:2000],
                "category": hit.get("category", ""),
            }
            for hit in gen_result.get("hits", [])
        ]
    result.stage_latencies_ms["retrieve_generate"] = round(
        (time.perf_counter() - stage_start) * 1000, 1
    )

    result.total_latency_ms = round((time.perf_counter() - pipeline_start) * 1000, 1)

    logger.info(
        "pipeline.completed",
        question_length=len(question),
        total_latency_ms=result.total_latency_ms,
        stage_latencies_ms=result.stage_latencies_ms,
        fallback=result.fallback,
        answer_length=len(result.answer),
    )
    return result
