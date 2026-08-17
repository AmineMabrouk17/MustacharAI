"""Tests for the ingestion pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mustachar.pipeline.ingestion import chunk_by_articles, parse_pdf

if TYPE_CHECKING:
    from pathlib import Path

SAMPLE_TEXT = """\
ال法则 العامة
المادة 1 - هذا القانون ينظم hoạtت المحاكم.
المادة 2 - تطبق أحكام هذا القانون على جميع الموظفين.
المادة 3 - يُعدّ مخالفاً من حادث على هذه الأحكام.
"""


def test_chunk_by_articles_returns_correct_count() -> None:
    chunks = chunk_by_articles(SAMPLE_TEXT)
    assert len(chunks) == 4


def test_chunk_by_articles_preamble() -> None:
    chunks = chunk_by_articles(SAMPLE_TEXT)
    assert chunks[0]["article"] == "مقدمة"
    assert "ال法则" in chunks[0]["content"]


def test_chunk_by_articles_numbers() -> None:
    chunks = chunk_by_articles(SAMPLE_TEXT)
    article_chunks = [c for c in chunks if c["article"].startswith("المادة")]
    assert len(article_chunks) == 3


def test_chunk_by_articles_empty() -> None:
    assert chunk_by_articles("") == []


def test_chunk_by_articles_no_markers() -> None:
    chunks = chunk_by_articles("some plain text without article markers")
    assert len(chunks) == 1
    assert chunks[0]["article"] == "全文"


def test_parse_pdf(tmp_path: Path) -> None:
    try:
        from pypdf import PdfWriter
    except ImportError:
        from PyPDF2 import PdfWriter  # type: ignore[no-redef]

    pdf_path = tmp_path / "test.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    result = parse_pdf(pdf_path)
    assert isinstance(result, str)
