"""Tests for the index CLI command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mustachar.cli.index import _collect_pdfs, build_parser

if TYPE_CHECKING:
    from pathlib import Path


def test_collect_pdfs_single_file(tmp_path: Path) -> None:
    pdf = tmp_path / "law.pdf"
    pdf.write_text("fake")
    result = _collect_pdfs(str(pdf), None)
    assert result == [pdf]


def test_collect_pdfs_directory(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_text("a")
    (tmp_path / "b.pdf").write_text("b")
    (tmp_path / "c.txt").write_text("c")
    result = _collect_pdfs(None, str(tmp_path))
    assert len(result) == 2


def test_collect_pdfs_no_input() -> None:
    try:
        _collect_pdfs(None, None)
    except SystemExit as e:
        assert e.code == 1


def test_collect_pdfs_missing_file() -> None:
    try:
        _collect_pdfs("/nonexistent/file.pdf", None)
    except SystemExit as e:
        assert e.code == 1


def test_build_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["--file", "test.pdf"])
    assert args.file == "test.pdf"
    assert args.category == ""
    assert args.dry_run is False


def test_build_parser_dry_run() -> None:
    parser = build_parser()
    args = parser.parse_args(["--file", "test.pdf", "--dry-run", "--category", "test"])
    assert args.dry_run is True
    assert args.category == "test"


def test_collect_pdfs_rejects_non_pdf(tmp_path: Path) -> None:
    txt = tmp_path / "doc.txt"
    txt.write_text("not a pdf")
    try:
        _collect_pdfs(str(txt), None)
    except SystemExit as e:
        assert e.code == 1
