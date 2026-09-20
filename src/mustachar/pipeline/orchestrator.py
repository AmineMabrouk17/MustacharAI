"""Text RAG pipeline orchestrator: Reformulate → Retrieve → Generate."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from mustachar.pipeline.generator import FALLBACK_FRENCH, generate
from mustachar.pipeline.reformulator import reformulate

logger = structlog.get_logger()

FALLBACK_GENERATE = FALLBACK_FRENCH


@dataclass
class PipelineResult:
    """Full pipeline result with per-stage latency tracking."""

    question: str = ""
    reformulated_query: str = ""
    answer: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    fallback: bool = True
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
    stage_start = time.perf_counter()
    try:
        gen_result = await generate(search_query)
    except Exception:
        logger.exception("pipeline.generate_error")
        result.answer = FALLBACK_GENERATE
        result.fallback = True
        result.citations = []
    else:
        result.answer = gen_result.get("answer", FALLBACK_GENERATE)
        result.fallback = gen_result.get("fallback", True)
        result.citations = [
            {
                "source": hit.get("source", ""),
                "article": hit.get("article", ""),
                "content": hit.get("content", "")[:200],
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