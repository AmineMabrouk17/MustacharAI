"""RAG evaluation harness: runs every Darja QA pair through the live pipeline.

Offline command-line scorer for ``tests/test_qa_pairs.md``. Each query is sent
through reformulation -> retrieval -> generation and scored pass/fail on
grounding, Fasl/Majalla citation presence, and expected fallback behaviour for
out-of-scope/vague questions. Prints a stable, repeatable per-query table and a
summary score so retrieval/generation changes can be compared before/after.

Usage::

    python -m mustachar.cli.score
    python -m mustachar.cli.score --qa-file tests/test_qa_pairs.md --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from mustachar.core.logging import setup_logging
from mustachar.pipeline.generator import generate
from mustachar.pipeline.reformulator import reformulate

logger = structlog.get_logger()

SECTION_RE = re.compile(r"(?m)^(##\s+.*)$")
QA_RE = re.compile(r"(?m)^(###\s+Q\d+.*)$")
QA_HEADING_RE = re.compile(r"^\s*###\s+(Q\d+)\s+[—-]\s+(.*)$")
FIELD_RE = re.compile(r"^\*\*(?P<key>.*?):\*\*\s*(?P<val>.*)$")
ARABIC_RE = re.compile(r"[\u0600-\u06FF]+")

CITATION_HINTS = ("فصل", "المادة", "مادة", "مجلة")

FALLBACK_QIDS = {"Q24", "Q25"}

MAX_ATTEMPTS = 3
RETRY_DELAY_MS = 2000


@dataclass
class QAPair:
    """One parsed test query with its expected answer metadata."""

    qid: str
    query: str
    expected: str
    article_ref: str
    category: str = ""
    expect_fallback: bool = False


@dataclass
class QAScore:
    """Pass/fail result for a single query."""

    qid: str
    query: str
    fallback_ok: bool | None
    grounded: bool | None
    citation_ok: bool | None
    principle_ok: bool | None

    @property
    def expect_fallback(self) -> bool:
        return self.citation_ok is None and self.principle_ok is None

    @property
    def passed(self) -> bool:
        checks = [self.fallback_ok, self.grounded]
        if not self.expect_fallback:
            checks += [self.citation_ok, self.principle_ok]
        return all(c is not False for c in checks)


def _section_title(heading: str) -> str:
    title = re.sub(r"^##\s+", "", heading.strip())
    return re.sub(r"^\d+\.\s*", "", title)


def _parse_pair(heading: str, body: str, category: str) -> QAPair:
    """Parse one ``### Qn`` block into a QAPair."""
    m = QA_HEADING_RE.match(heading)
    assert m is not None, f"unexpected QA heading: {heading!r}"
    qid = m.group(1)
    heading_query = m.group(2).strip()

    fields: dict[str, str] = {}
    for line in body.splitlines():
        fm = FIELD_RE.match(line)
        if fm:
            key = fm.group("key").strip()
            if key not in fields:
                fields[key] = fm.group("val").strip()

    query = fields.get("Query", heading_query)
    expected = fields.get("Expected", "")
    article_ref = fields.get("Article ref", "")
    expect_fallback = qid in FALLBACK_QIDS or "Expected fallback" in fields
    return QAPair(
        qid=qid,
        query=query,
        expected=expected,
        article_ref=article_ref,
        category=category,
        expect_fallback=expect_fallback,
    )


def parse_qa_pairs(path: Path) -> list[QAPair]:
    """Parse every ``### Qn`` block out of ``tests/test_qa_pairs.md``."""
    text = path.read_text(encoding="utf-8")
    sections = SECTION_RE.split(text)
    pairs: list[QAPair] = []
    for i in range(1, len(sections), 2):
        category = _section_title(sections[i])
        body = sections[i + 1] if i + 1 < len(sections) else ""
        parts = QA_RE.split(body)
        for j in range(1, len(parts), 2):
            q_heading = parts[j]
            q_body = parts[j + 1] if j + 1 < len(parts) else ""
            pairs.append(_parse_pair(q_heading, q_body, category))
    return pairs


def _normalize_arabic(token: str) -> str:
    """Normalize a token for lenient root matching across inflections."""
    t = "".join(ch for ch in token if "\u0600" <= ch <= "\u06FF")
    t = t.replace("\u0622", "\u0627").replace("\u0623", "\u0627").replace("\u0625", "\u0627")
    t = t.replace("\u0629", "")
    for prefix in ("\u0648\u0627\u0644", "\u0641\u0627\u0644", "\u0627\u0644"):
        if t.startswith(prefix):
            t = t[len(prefix) :]
            break
    return t


def _ar_content_words(text: str) -> set[str]:
    """Extract normalized Arabic content words (drops non-Arabic garbage)."""
    words: set[str] = set()
    for token in ARABIC_RE.findall(text):
        if len(token) < 4:
            continue
        norm = _normalize_arabic(token)
        if len(norm) >= 3:
            words.add(norm)
    return words


def _shares_principle(answer: str, expected: str) -> bool:
    """True when an answer shares a root word with the expected principle."""
    expected_words = _ar_content_words(expected)
    if not expected_words:
        return True
    answer_words = _ar_content_words(answer)
    for e in expected_words:
        for a in answer_words:
            if e in a or a in e:
                return True
    return False


def _mentions_citation(answer: str, hits: list[dict[str, Any]]) -> bool:
    """True when the answer references a Fasl/Majalla article citation."""
    if not answer:
        return False
    for hit in hits:
        article = hit.get("article", "")
        if article and article in answer:
            return True
    return any(hint in answer for hint in CITATION_HINTS)


def score_pair(
    qa: QAPair,
    *,
    answer: str,
    hits: list[dict[str, Any]],
    fallback: bool,
) -> QAScore:
    """Score one answer against its expected checks."""
    answered = bool(answer.strip())
    if qa.expect_fallback:
        return QAScore(
            qid=qa.qid,
            query=qa.query,
            fallback_ok=bool(fallback),
            grounded=bool(fallback and answered),
            citation_ok=None,
            principle_ok=None,
        )
    return QAScore(
        qid=qa.qid,
        query=qa.query,
        fallback_ok=not fallback,
        grounded=bool(answered and hits),
        citation_ok=_mentions_citation(answer, hits),
        principle_ok=_shares_principle(answer, qa.expected),
    )


async def _with_retry(
    operation: Any,
    *args: Any,
    attempts: int = MAX_ATTEMPTS,
    delay_ms: int = RETRY_DELAY_MS,
) -> Any:
    """Run an async pipeline call, retrying transient failures.

    A transient network error must not silently turn into a wrong score; a
    couple of quick retries make the harness output stable and repeatable.
    The final failure propagates so the caller can fail-closed.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await operation(*args)
        except Exception:
            if attempt == attempts:
                raise
            await asyncio.sleep(delay_ms * attempt / 1000)
    raise AssertionError("unreachable")  # pragma: no cover


async def _evaluate_pair(qa: QAPair) -> QAScore:
    """Run one query through the live pipeline and score it."""
    try:
        ref = await _with_retry(reformulate, qa.query)
    except Exception:
        logger.warning("score.reformulate_error", qid=qa.qid)
        ref = {}
    primary = ref.get("primary_query", "") if isinstance(ref, dict) else ""
    search_query = str(primary).strip() or qa.query

    try:
        gen = await _with_retry(generate, search_query)
    except Exception:
        logger.exception("score.generate_error", qid=qa.qid)
        return score_pair(qa, answer="", hits=[], fallback=True)

    answer = gen.get("answer", "")
    raw_hits = gen.get("hits", [])
    hits = raw_hits if isinstance(raw_hits, list) else []
    fallback = bool(gen.get("fallback", True))
    return score_pair(qa, answer=answer, hits=hits, fallback=fallback)


def _check(c: bool | None) -> str:
    return "pass" if c is None else ("pass" if c else "fail")


def print_report(scores: list[QAScore]) -> None:
    """Print a stable per-query table plus summary score."""
    print(f"{'Query':<6}{'Fallback':<9}{'Grounded':<9}{'Citation':<9}{'Principle':<10}Result")
    for s in scores:
        result = "PASS" if s.passed else "FAIL"
        print(
            f"{s.qid:<6}{_check(s.fallback_ok):<9}{_check(s.grounded):<9}"
            f"{_check(s.citation_ok):<9}{_check(s.principle_ok):<10}{result}"
        )

    total = len(scores)
    passed = sum(1 for s in scores if s.passed)
    fallback_expected = [s for s in scores if s.expect_fallback]
    non_fallback = [s for s in scores if not s.expect_fallback]
    grounded_expected = sum(1 for s in non_fallback if s.grounded)
    fallback_passed = sum(1 for s in fallback_expected if s.grounded)

    print(f"\nScore: {passed}/{total} queries passed")
    print(f"Grounded non-fallback: {grounded_expected}/{len(non_fallback)}")
    print(f"Expected fallback responses: {fallback_passed}/{len(fallback_expected)}")


def to_jsonable(scores: list[QAScore]) -> dict[str, Any]:
    """Machine-readable summary for diffing between pipeline versions."""
    return {
        "total": len(scores),
        "passed": sum(1 for s in scores if s.passed),
        "results": [
            {
                "qid": s.qid,
                "fallback_ok": s.fallback_ok,
                "grounded": s.grounded,
                "citation_ok": s.citation_ok,
                "principle_ok": s.principle_ok,
                "passed": s.passed,
            }
            for s in scores
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the score command."""
    parser = argparse.ArgumentParser(
        prog="mustachar score",
        description="Run every Darja QA pair through the live RAG pipeline and score it.",
    )
    parser.add_argument(
        "--qa-file",
        type=str,
        default="tests/test_qa_pairs.md",
        help="Path to the QA pairs markdown file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print results as JSON for machine-readable diffing.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the score CLI command."""
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    qa_path = Path(args.qa_file)
    if not qa_path.is_file():
        logger.error("qa_file_not_found", path=str(qa_path))
        sys.exit(1)

    pairs = parse_qa_pairs(qa_path)
    if not pairs:
        logger.error("no_qa_pairs_found", path=str(qa_path))
        sys.exit(1)

    logger.info("score_starting", query_count=len(pairs), qa_file=str(qa_path))
    scores = asyncio.run(_run_all(pairs))

    if args.json:
        print(json.dumps(to_jsonable(scores), ensure_ascii=False, indent=2))
    else:
        print_report(scores)


async def _run_all(pairs: list[QAPair]) -> list[QAScore]:
    scores: list[QAScore] = []
    for qa in pairs:
        logger.info("score_query_start", qid=qa.qid)
        scores.append(await _evaluate_pair(qa))
        logger.info("score_query_done", qid=qa.qid)
    return scores


if __name__ == "__main__":
    main()
