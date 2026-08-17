"""PDF ingestion pipeline: parse, chunk, embed, store."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

from mustachar.infra.chroma_client import get_chroma_client, get_or_create_collection

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger()

ARTICLE_PATTERN = re.compile(
    r"(?:المادة|مادة)\s+(\d+)",
    re.UNICODE,
)


def parse_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF file."""
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader  # type: ignore[import-not-found,no-redef]

    reader = PdfReader(str(pdf_path))
    pages_text: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)
    return "\n".join(pages_text)


def chunk_by_articles(text: str) -> list[dict[str, str]]:
    """Split text into chunks by Arabic article markers."""
    matches = list(ARTICLE_PATTERN.finditer(text))
    if not matches:
        return [{"article": "全文", "content": text.strip()}] if text.strip() else []

    chunks: list[dict[str, str]] = []

    preamble = text[: matches[0].start()].strip()
    if preamble:
        chunks.append({"article": "مقدمة", "content": preamble})

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            article_num = match.group(1)
            chunks.append({"article": f"المادة {article_num}", "content": content})

    return chunks


def ingest_pdfs(
    paths: list[Path],
    category: str = "",
    dry_run: bool = False,
) -> list[dict[str, str]]:
    """Parse PDFs, chunk by articles, embed and store in ChromaDB."""
    all_chunks: list[dict[str, str]] = []

    for pdf_path in paths:
        logger.info("parsing_pdf", path=str(pdf_path))
        text = parse_pdf(pdf_path)
        chunks = chunk_by_articles(text)

        for chunk in chunks:
            chunk["source"] = pdf_path.name
            if category:
                chunk["category"] = category

        all_chunks.extend(chunks)

    if dry_run:
        for chunk in all_chunks:
            logger.info(
                "dry_run_chunk",
                article=chunk.get("article", ""),
                source=chunk.get("source", ""),
                preview=chunk["content"][:120],
            )
        return all_chunks

    if not all_chunks:
        return []

    ids = [
        f"{c.get('source', 'unknown')}_{c.get('article', str(i))}"
        for i, c in enumerate(all_chunks)
    ]
    documents = [c["content"] for c in all_chunks]
    metadatas: list[dict[str, Any]] = [
        {
            "source": c.get("source", ""),
            "article": c.get("article", ""),
            "category": c.get("category", ""),
        }
        for c in all_chunks
    ]

    client = get_chroma_client()
    collection = get_or_create_collection(client)

    batch_size = 100
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i : i + batch_size]
        batch_ids = ids[i : i + batch_size]
        batch_meta = metadatas[i : i + batch_size]
        collection.add(
            documents=batch_docs,
            ids=batch_ids,
            metadatas=batch_meta,
        )
        logger.info("batch_stored", count=len(batch_docs), offset=i)

    logger.info("ingestion_complete", total_chunks=len(all_chunks))
    return all_chunks
