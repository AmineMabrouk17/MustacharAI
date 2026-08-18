"""Full RAG pipeline orchestrator: STT → Reformulate → Retrieve → Generate → TTS."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from mustachar.pipeline.generator import generate
from mustachar.pipeline.reformulator import reformulate
from mustachar.pipeline.stt import speech_to_text

logger = structlog.get_logger()

FALLBACK_STT = "ما فهمتش الصوت. حاول مرة أخرى أحسن."
FALLBACK_REFORMULATE = "ما نجمتش نفهم السؤال. حاول أعادة صياغته."
FALLBACK_RETRIEVE = "ما لقيتش معلومات في القانون على هالسؤال."
FALLBACK_GENERATE = (
    "ما لقيتش معلومات كافية في القانون على هالسؤال. حلّي تسأل محامي باش يعطيك إجابة أدق."
)
FALLBACK_TTS = "صارت مشكلة في تحويل الجواب لصوت."


@dataclass
class PipelineResult:
    """Full pipeline result with per-stage latency tracking."""

    transcript: str = ""
    reformulated_query: str = ""
    answer: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    fallback: bool = True
    stage_latencies_ms: dict[str, float] = field(default_factory=dict)
    total_latency_ms: float = 0.0


async def run_pipeline(
    audio_bytes: bytes,
    filename: str = "audio.webm",
) -> PipelineResult:
    """Execute the full voice-to-voice RAG pipeline.

    Stages:
      1. STT — speech-to-text (Darja transcript)
      2. Reformulate — Darja → MSA legal query
      3. Retrieve — vector search over legal corpus
      4. Generate — grounded LLM answer
      5. TTS — text-to-speech (not collected here; streaming handled by caller)

    Each stage has independent error handling with per-stage Darja fallback
    messages and structured JSON latency logging.
    """
    pipeline_start = time.perf_counter()
    result = PipelineResult()

    # ── Stage 1: STT ──────────────────────────────────────────────
    stage_start = time.perf_counter()
    try:
        result.transcript = await speech_to_text(audio_bytes, filename)
    except Exception:
        logger.exception("pipeline.stt_error")
        result.transcript = ""
        result.answer = FALLBACK_STT
        result.fallback = True
        result.stage_latencies_ms["stt"] = round(
            (time.perf_counter() - stage_start) * 1000, 1
        )
        result.total_latency_ms = round(
            (time.perf_counter() - pipeline_start) * 1000, 1
        )
        return result
    result.stage_latencies_ms["stt"] = round(
        (time.perf_counter() - stage_start) * 1000, 1
    )

    if not result.transcript:
        result.answer = FALLBACK_STT
        result.total_latency_ms = round(
            (time.perf_counter() - pipeline_start) * 1000, 1
        )
        return result

    # ── Stage 2: Reformulate ──────────────────────────────────────
    stage_start = time.perf_counter()
    try:
        reformulated = await reformulate(result.transcript)
    except Exception:
        logger.exception("pipeline.reformulate_error")
        result.reformulated_query = ""
        result.stage_latencies_ms["reformulate"] = round(
            (time.perf_counter() - stage_start) * 1000, 1
        )
    else:
        result.reformulated_query = reformulated.get("primary_query", "")
        result.stage_latencies_ms["reformulate"] = reformulated.get(
            "latency_ms", 0.0
        )

    search_query = result.reformulated_query or result.transcript

    # ── Stage 3 + 4: Retrieve + Generate ──────────────────────────
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
            }
            for hit in gen_result.get("hits", [])
        ]
    result.stage_latencies_ms["retrieve_generate"] = round(
        (time.perf_counter() - stage_start) * 1000, 1
    )

    result.total_latency_ms = round(
        (time.perf_counter() - pipeline_start) * 1000, 1
    )

    logger.info(
        "pipeline.completed",
        total_latency_ms=result.total_latency_ms,
        stage_latencies_ms=result.stage_latencies_ms,
        fallback=result.fallback,
        answer_length=len(result.answer),
    )

    return result
