"""Tests for the CLI RAG evaluation harness."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from mustachar.cli.score import (
    MAX_ATTEMPTS,
    QAPair,
    _ar_content_words,
    _mentions_citation,
    _normalize_arabic,
    _shares_principle,
    _with_retry,
    parse_qa_pairs,
    score_pair,
)

if TYPE_CHECKING:
    from pathlib import Path

QA_MARKDOWN = """\
# MustacharAI — Legal Q&A Test Pairs

## 1. قانون الالتزامات والعقود

### Q1 — ما هي العقدة وأركانها الأساسية؟
**Expected:** العقد هو اتفاق طرفين على تأثير التزام. أركانه: التراضي، الأهلية.
**Article ref:** المادة 1 من قانون الالتزامات والعقود.

### Q2 — كيفاش تعمل الإقالة في القانون التونسي؟
**Expected:** الإقالة هي اتفاق على إلغاء العقد.
**Article ref:** فصل من قانون الالتزامات والعقود.

## 8. أسئلة متنوعة

### Q24 — سؤال مالوش علاقة بالقانون
**Query:** وشachel PSG في آخر مباراة؟
**Expected:** لا يجب أن يجيب بنص قانوني.
**Expected fallback:** "ما لقيتش معلومات قانونية على هذا السؤال."

### Q25 — سؤال م模糊
**Query:** قانون
**Expected:** قد يحتاج للسؤال أو يُرجع برسالة تطلب توضيح.
"""


def _qa_pair(qid: str, *, expect_fallback: bool = False) -> QAPair:
    return QAPair(
        qid=qid,
        query="سؤال",
        expected="العقد اتفاق والأهلية المعاملة.",
        article_ref="المادة 1",
        expect_fallback=expect_fallback,
    )


def test_parse_qa_pairs_loads_all_queries(tmp_path: Path) -> None:
    qa_path = tmp_path / "test_qa_pairs.md"
    qa_path.write_text(QA_MARKDOWN, encoding="utf-8")
    pairs = parse_qa_pairs(qa_path)
    assert [p.qid for p in pairs] == ["Q1", "Q2", "Q24", "Q25"]
    assert pairs[0].query == "ما هي العقدة وأركانها الأساسية؟"
    assert pairs[0].expect_fallback is False
    assert "اتفاق" in pairs[0].expected
    assert pairs[0].category == "قانون الالتزامات والعقود"


def test_parse_qa_pairs_query_field_overrides_heading(tmp_path: Path) -> None:
    qa_path = tmp_path / "test_qa_pairs.md"
    qa_path.write_text(QA_MARKDOWN, encoding="utf-8")
    pairs = parse_qa_pairs(qa_path)
    q24 = pairs[2]
    assert q24.query == "وشachel PSG في آخر مباراة؟"
    assert q24.expect_fallback is True
    q25 = pairs[3]
    assert q25.query == "قانون"
    assert q25.expect_fallback is True


def test_ar_content_words_ignores_non_arabic_and_short_tokens() -> None:
    words = _ar_content_words("القانون Tunisian MSA عقد والالتزامات")
    assert "قانون" in words
    assert "التزامات" in words
    assert all(len(w) >= 3 for w in words)


def test_normalize_arabic_unifies_alef_and_drops_prefix() -> None:
    assert _normalize_arabic("الإقالة") == "اقال"
    assert _normalize_arabic("الأهلية") == "اهلي"
    assert _normalize_arabic("ابيها") == "ابيها"


def test_shares_principle_matches_nearby_inflections() -> None:
    assert _shares_principle("بشأن اقالة العقد", "الإقالة اتفاق على إلغاء العقد")


def test_shares_principle_finds_root_overlap() -> None:
    assert _shares_principle("في العقد القانون", "العقدة اتفاق وأركان")
    assert not _shares_principle("لا يمكن أن يكون", "القتل العقوبة")


def test_mentions_citation_uses_hit_article() -> None:
    hits: list[dict[str, Any]] = [{"article": "المادة 12"}]
    assert _mentions_citation("نص المادة 12 من المجلة", hits)
    assert _mentions_citation("ينص الفصل على ذلك", [])
    assert not _mentions_citation("الجواب فقط", [])


def test_score_pair_grounded_passes() -> None:
    qa = _qa_pair("Q1")
    score = score_pair(
        qa,
        answer="العقد اتفاق بين الطرفين من المادة 1.",
        hits=[{"article": "المادة 1"}],
        fallback=False,
    )
    assert score.passed is True
    assert score.fallback_ok is True
    assert score.grounded is True
    assert score.citation_ok is True
    assert score.principle_ok is True


def test_score_pair_grounded_fails_on_fallback() -> None:
    qa = _qa_pair("Q1")
    score = score_pair(
        qa,
        answer="ما لقيتش معلومات كافية في القانون.",
        hits=[],
        fallback=True,
    )
    assert score.passed is False
    assert score.fallback_ok is False
    assert score.grounded is False


def test_score_pair_fallback_expected_passes() -> None:
    qa = _qa_pair("Q24", expect_fallback=True)
    score = score_pair(
        qa,
        answer="ما لقيتش معلومات قانونية على هذا السؤال.",
        hits=[],
        fallback=True,
    )
    assert score.passed is True
    assert score.fallback_ok is True
    assert score.grounded is True
    assert score.citation_ok is None
    assert score.principle_ok is None


def test_score_pair_fallback_expected_fails_when_grounded_answer() -> None:
    qa = _qa_pair("Q24", expect_fallback=True)
    score = score_pair(
        qa,
        answer="PSG فاز في المباراة.",
        hits=[{"article": "المادة 1"}],
        fallback=False,
    )
    assert score.passed is False
    assert score.fallback_ok is False


class _Flaky:
    """Async callable that fails for the first ``failures`` invocations."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("transient")
        return "ok"


@pytest.mark.asyncio
async def test_with_retry_succeeds_after_transient_failures() -> None:
    flaky = _Flaky(failures=2)
    assert await _with_retry(flaky, attempts=3, delay_ms=1) == "ok"
    assert flaky.calls == 3


@pytest.mark.asyncio
async def test_with_retry_raises_after_max_attempts() -> None:
    flaky = _Flaky(failures=MAX_ATTEMPTS)
    with pytest.raises(RuntimeError):
        await _with_retry(flaky, attempts=MAX_ATTEMPTS, delay_ms=1)
    assert flaky.calls == MAX_ATTEMPTS


class _EmptyFirst:
    """Async callable returning an unusable empty string on the first call."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        return "" if self.calls == 1 else "usable"


class _AlwaysEmpty:
    """Async callable whose result is never usable."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        return ""


@pytest.mark.asyncio
async def test_with_retry_retries_invalid_result() -> None:
    empty_first = _EmptyFirst()
    assert (
        await _with_retry(empty_first, attempts=3, delay_ms=1, ok=bool) == "usable"
    )
    assert empty_first.calls == 2


@pytest.mark.asyncio
async def test_with_retry_returns_last_result_when_all_invalid() -> None:
    always_empty = _AlwaysEmpty()
    assert (
        await _with_retry(always_empty, attempts=3, delay_ms=1, ok=bool) == ""
    )
    assert always_empty.calls == 3
