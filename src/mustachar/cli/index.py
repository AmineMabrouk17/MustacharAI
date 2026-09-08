"""CLI command for ingesting legal PDFs into ChromaDB."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import structlog

from mustachar.core.logging import setup_logging
from mustachar.infra.chroma_client import get_chroma_client
from mustachar.pipeline.ingestion import ingest_pdfs

logger = structlog.get_logger()


def _load_manifest(manifest_path: str) -> dict[str, str]:
    """Map PDF filenames to categories from a ``filename,category`` CSV."""
    with open(manifest_path, encoding="utf-8") as f:
        return {row["filename"]: row["category"] for row in csv.DictReader(f)}


def _collect_pdfs(file: str | None, dir_path: str | None) -> list[Path]:
    """Resolve file/dir arguments into a list of PDF paths."""
    if file:
        p = Path(file)
        if not p.is_file():
            logger.error("file_not_found", path=file)
            sys.exit(1)
        if p.suffix.lower() != ".pdf":
            logger.error("not_a_pdf", path=file)
            sys.exit(1)
        return [p]

    if dir_path:
        d = Path(dir_path)
        if not d.is_dir():
            logger.error("dir_not_found", path=dir_path)
            sys.exit(1)
        pdfs = sorted(d.glob("*.pdf"))
        if not pdfs:
            logger.error("no_pdfs_in_dir", path=dir_path)
            sys.exit(1)
        return pdfs

    logger.error("no_input_provided")
    sys.exit(1)


def _reset_collection() -> None:
    """Delete the legal_corpus collection so it can be re-created fresh."""
    client = get_chroma_client()
    try:
        client.delete_collection("legal_corpus")
    except Exception:
        logger.warning("collection_not_found_during_reset")
    logger.info("collection_reset", name="legal_corpus")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the index command."""
    parser = argparse.ArgumentParser(
        prog="mustachar index",
        description="Ingest legal PDFs into ChromaDB.",
    )
    parser.add_argument("--file", type=str, help="Path to a single PDF file.")
    parser.add_argument("--dir", type=str, help="Path to a directory of PDFs.")
    parser.add_argument(
        "--category",
        type=str,
        default="",
        help="Category tag for metadata.",
    )
    parser.add_argument(
        "--manifest",
        type=str,
        help="Path to a filename,category CSV to tag each PDF.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the collection before ingesting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show parsed articles without writing to DB.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the index CLI command."""
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    paths = _collect_pdfs(args.file, args.dir)
    if args.reset:
        _reset_collection()

    manifest = _load_manifest(args.manifest) if args.manifest else {}
    groups: dict[str, list[Path]] = {}
    for p in paths:
        category = manifest.get(p.name, args.category)
        groups.setdefault(category, []).append(p)

    logger.info("starting_ingestion", file_count=len(paths))

    total_chunks = 0
    for category, group_paths in groups.items():
        chunks = ingest_pdfs(
            paths=group_paths,
            category=category,
            dry_run=args.dry_run,
        )
        total_chunks += len(chunks)

    if args.dry_run:
        print(f"\nDry run complete: {total_chunks} article(s) parsed.")
    else:
        print(f"\nIngestion complete: {total_chunks} article(s) stored in ChromaDB.")


if __name__ == "__main__":
    main()
