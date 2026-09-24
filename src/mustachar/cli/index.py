"""CLI command for ingesting legal documents (.txt / .pdf) into ChromaDB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import structlog

from mustachar.core.logging import setup_logging
from mustachar.core.settings import settings
from mustachar.infra.chroma_client import get_chroma_client, get_or_create_collection
from mustachar.pipeline.ingestion import chunk_legal_text, extract_text_from_bytes

logger = structlog.get_logger()

# Canonical Arabic names and legal categories for the 15 Tunisian codes
CANONICAL_NAMES: dict[str, dict[str, str]] = {
    "constitution-2022": {"source": "دستور الجمهورية التونسية 2022", "category": "دستوري"},
    "COCArabe": {"source": "مجلة الالتزامات والعقود", "category": "مدني"},
    "PenalArabe": {"source": "المجلة الجزائية", "category": "جزائي"},
    "CommerceArabe": {"source": "المجلة التجارية", "category": "تجاري"},
    "StatutpersonnelArabe": {"source": "مجلة الأحوال الشخصية", "category": "أحوال شخصية"},
    "travailArabe": {"source": "مجلة الشغل", "category": "شغل واجتماعي"},
    "ProcedurecivilecomArabe": {"source": "مجلة المرافعات المدنية والتجارية", "category": "إجراءات"},
    "ProcedurepenaleArabe": {"source": "مجلة الإجراءات الجزائية", "category": "إجراءات جزائية"},
    "societeArabe": {"source": "مجلة الشركات التجارية", "category": "تجاري"},
    "EnfantArabe": {"source": "مجلة حماية الطفل", "category": "حماية الطفل"},
    "NationaliteArabe": {"source": "مجلة الجنسية التونسية", "category": "جنسية"},
    "dtreelArabe": {"source": "مجلة الحقوق العينية", "category": "حقوق عينية وعقارات"},
    "ArbitrageArabe": {"source": "مجلة التحكيم", "category": "تحكيم"},
    "DIPArabe": {"source": "مجلة القانون الدولي الخاص", "category": "دولي خاص"},
    "115725": {"source": "مرسوم قانوني تونسي", "category": "مراسيم وقوانين"},
}


def _collect_files(file: str | None, dir_path: str | None) -> list[Path]:
    """Resolve file/dir arguments into a list of .txt or .pdf paths."""
    valid_suffixes = {".txt", ".pdf"}

    if file:
        p = Path(file)
        if not p.is_file():
            logger.error("file_not_found", path=file)
            sys.exit(1)
        if p.suffix.lower() not in valid_suffixes:
            logger.error("unsupported_extension", path=file)
            sys.exit(1)
        return [p]

    if dir_path:
        d = Path(dir_path)
        if not d.is_dir():
            logger.error("dir_not_found", path=dir_path)
            sys.exit(1)
        files = sorted([f for f in d.iterdir() if f.suffix.lower() in valid_suffixes])
        if not files:
            logger.error("no_valid_files_in_dir", path=dir_path)
            sys.exit(1)
        return files

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
        description="Ingest Tunisian legal codes (.txt / .pdf) into ChromaDB.",
    )
    parser.add_argument("--file", type=str, help="Path to a single .txt or .pdf file.")
    parser.add_argument("--dir", type=str, help="Path to a directory containing codes.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing ChromaDB collection before starting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show parsed article counts without writing to ChromaDB.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the index CLI command."""
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    files = _collect_files(args.file, args.dir)

    if args.reset:
        _reset_collection()

    logger.info("starting_ingestion", file_count=len(files))

    all_chunks: list[dict[str, Any]] = []
    for file_path in files:
        stem = file_path.stem
        meta_info = CANONICAL_NAMES.get(stem, {"source": stem, "category": "قانون تونسي"})
        source_name = meta_info["source"]
        category_name = meta_info["category"]

        file_bytes = file_path.read_bytes()
        text = extract_text_from_bytes(file_bytes, file_path.name)
        docs = chunk_legal_text(text, file_path.name)

        # Enrich metadata (chunks are plain dicts from ingestion.py)
        for chunk in docs:
            chunk["source"] = source_name
            chunk["category"] = category_name

        print(f"  ✓ {source_name}: استخراج {len(docs)} فصلاً قانونياً.")
        all_chunks.extend(docs)

    print(f"\n📊 إجمالي الفصول المستخرجة: {len(all_chunks)}")

    if args.dry_run:
        print("Dry run complete: No documents written to ChromaDB.")
        return

    print("⏳ جاري الفهرسة والتوليد المتجهي في ChromaDB...")

    client = get_chroma_client()
    collection = get_or_create_collection(client)

    ids = [
        f"{Path(c.get('source', 'unknown')).stem}_{i}"
        for i, c in enumerate(all_chunks)
    ]
    documents = [c["content"] for c in all_chunks]
    metadatas: list[dict[str, str]] = [
        {
            "source": c.get("source", ""),
            "article": c.get("article", ""),
            "category": c.get("category", ""),
        }
        for c in all_chunks
    ]

    # Batch add in chunks of 100 to ensure fast, stable ingestion
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        collection.add(
            documents=documents[i : i + batch_size],
            ids=ids[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )
        print(
            f"  --> فهرسة الدفعة {i // batch_size + 1} / "
            f"{(len(documents) + batch_size - 1) // batch_size}"
        )

    print(f"\n✅ تمت فهرسة كامل المجلات القانونية بنجاح في '{settings.chroma_persist_dir}'!")


if __name__ == "__main__":
    main()
