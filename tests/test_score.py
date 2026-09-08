"""Tests for the CLI RAG evaluation harness."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from mustachar.cli.score import (
    MAX_ATTEMPTS,
    QAPair,
    _ar_content_words,
    _fr_content_words,
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
**Expected:** Le contrat est un accord entre deux parties destiné à créer des obligations.
**Article ref:** Art. 1 du Code des Obligations et des Contrats.

### Q2 — كيفاش تعمل الإقالة في القانون التونسي؟
**Expected:** La résiliation conventionnelle est un accord visant à dissoudre le contrat.
**Article ref:** Fasl du Code des Obligations et des Contrats.

## 8. أسئلة متنوعة

### Q24 — سؤال مالوش علاقة بالقانون
**Query:** وشachel PSG في آخر مباراة؟
**Expected:** Ne doit pas répondre par un texte juridique.
**Expected fallback:** "Je n'ai trouvé aucune information juridique sur cette question."

### Q25 — سؤال م模糊
**Query:** قانون
**Expected:** Il convient de demander des précisions.
"""


def _qa_pair(qid: str, *, expect_fallback: bool = False) -> QAPair:
    return QAPair(
        qid=qid,
        query="سؤال",
        expected="Le contrat exige le consentement et la capacité des parties.",
        article_ref="Art. 1",
        expect_fallback=expect_fallback,
    )


def test_parse_qa_pairs_loads_all_queries(tmp_path: Path) -> None:
    qa_path = tmp_path / "test_qa_pairs.md"
    qa_path.write_text(QA_MARKDOWN, encoding="utf-8")
    pairs = parse_qa_pairs(qa_path)
    assert [p.qid for p in pairs] == ["Q1", "Q2", "Q24", "Q25"]
    assert pairs[0].query == "ما هي العقدة وأركانها الأساسية؟"
    assert pairs[0].expect_fallback is False
    assert "contrat" in pairs[0].expected
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


def test_french_content_words_strips_accents_and_stopwords() -> None:
    words = _fr_content_words("Le contrat de la capacité selon le Code")
    assert "contrat" in words
    assert "capacite" in words
    assert "code" in words
    assert not any(w in words for w in ("le", "de", "la", "selon"))


def test_normalize_arabic_unifies_alef_and_drops_prefix() -> None:
    assert _normalize_arabic("الإقالة") == "اقال"
    assert _normalize_arabic("الأهلية") == "اهلي"
    assert _normalize_arabic("ابيها") == "ابيها"


def test_shares_principle_matches_nearby_inflections() -> None:
    assert _shares_principle("بشأن اقالة العقد", "الإقالة اتفاق على إلغاء العقد")


def test_shares_principle_finds_root_overlap() -> None:
    assert _shares_principle("في العقد القانون", "العقدة اتفاق وأركان")
    assert not _shares_principle("لا يمكن أن يكون", "القتل العقوبة")


def test_shares_principle_matches_french_content_words() -> None:
    assert _shares_principle(
        "Selon le fasl 5, le contrat exige la capacité des parties.",
        "Le contrat exige le consentement et la capacité des parties.",
    )
    assert not _shares_principle(
        "le mariage est conclu devant le notaire",
        "la peine varie selon la valeur du bien volé",
    )


def test_mentions_citation_uses_hit_article() -> None:
    hits: list[dict[str, Any]] = [{"article": "المادة 12"}]
    assert _mentions_citation("نص المادة 12 من المجلة", hits)
    assert _mentions_citation("ينص الفصل على ذلك", [])
    assert _mentions_citation("Selon le fasl 5 de la majalla", [])
    assert _mentions_citation("Réponse fondée sur l'article 2", [])
    assert not _mentions_citation("الجواب فقط", [])
    assert not _mentions_citation("La réponse seulement", [])


def test_score_pair_grounded_passes() -> None:
    qa = _qa_pair("Q1")
    score = score_pair(
        qa,
        answer="Le contrat exige le consentement et la capacité selon l'art. 1.",
        hits=[{"article": "Art. 1"}],
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
        answer="Je n'ai pas trouvé d'informations suffisantes dans le corpus juridique.",
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
        answer="Je n'ai trouvé aucune information juridique sur cette question.",
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
        answer="Le PSG a gagné le match.",
        hits=[{"article": "Art. 1"}],
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
    assert await _with_retry(empty_first, attempts=3, delay_ms=1, ok=bool) == "usable"
    assert empty_first.calls == 2


@pytest.mark.asyncio
async def test_with_retry_returns_last_result_when_all_invalid() -> None:
    always_empty = _AlwaysEmpty()
    assert await _with_retry(always_empty, attempts=3, delay_ms=1, ok=bool) == ""
    assert always_empty.calls == 3
