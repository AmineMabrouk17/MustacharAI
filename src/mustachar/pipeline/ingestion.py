"""Legal document ingestion pipeline: parse, chunk, embed, store."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import structlog

from mustachar.infra.chroma_client import get_chroma_client, get_or_create_collection

logger = structlog.get_logger()

# Regex to match Arabic and French legal articles
# Matches: الفصل 1 / الفصل الأول / الفصل التاسع والثمانون / المادة 1 / Article 1
# Delimiter class tolerates OCR artefacts ("الفصل 2.- texte", "الفصل 5 (نقح…")
# while still requiring start-of-line so inline references don't split.
ARTICLE_PATTERN = re.compile(
    r"(?:^|\n)\s*((?:الفصل\s+(?:[0-9۰-۹]+|الأول|الأوّل|الأولى|الثاني|الثّاني|الثالث|الثّالث|الرابع|الرّابع|الخامس|السادس|السّادس|السابع|السّابع|الثامن|التاسع|التّاسع|العاشر|[\u0621-\u064A\s]+?))|(?:المادة|مادة)\s+[0-9۰-۹]+|Article\s+\d+)(?:\s*[\n:\-–—.()؛;،]|\s*$)",
    re.UNICODE | re.MULTILINE,
)


def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract clean text from PDF or TXT bytes."""
    suffix = Path(filename).suffix.lower()

    if suffix == ".txt":
        return file_bytes.decode("utf-8", errors="replace")

    if suffix == ".pdf":
        text_parts: list[str] = []
        try:
            import fitz  # PyMuPDF
        except ImportError:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                text = (page.extract_text() or "").strip()
                if text:
                    text_parts.append(text)
            return "\n\n".join(text_parts)

        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for page in doc:
                text = page.get_text("text").strip()
                if text:
                    text_parts.append(text)
        return "\n\n".join(text_parts)

    raise ValueError(f"صيغة الملف غير مدعومة: {suffix}. يرجى رفع ملف .pdf أو .txt")


def chunk_legal_text(text: str, filename: str) -> list[Any]:
    """Chunk legal text cleanly by articles (الفصول / المواد)."""
    clean_text = re.sub(r"\r\n", "\n", text)
    clean_text = re.sub(r"[ \t]+", " ", clean_text)

    matches = list(ARTICLE_PATTERN.finditer(clean_text))

    chunks: list[dict[str, str]] = []
    source_name = Path(filename).stem

    # Fallback to paragraph chunking if regex finds no legal articles
    if not matches:
        paragraphs = [p.strip() for p in clean_text.split("\n\n") if len(p.strip()) > 40]
        for i, p in enumerate(paragraphs):
            chunks.append(
                {
                    "article": f"مقطع {i+1}",
                    "content": p,
                    "source": source_name,
                }
            )
        return chunks

    # Preamble / Introduction
    preamble = clean_text[: matches[0].start()].strip()
    if preamble:
        chunks.append(
            {
                "article": "توطئة / مقدمة",
                "content": preamble,
                "source": source_name,
            }
        )

    # Each Article
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(clean_text)

        article_title = match.group(1).strip().replace("\n", " ")
        article_title = re.sub(r"\s+", " ", article_title)
        content = clean_text[start:end].strip()

        if content:
            chunks.append(
                {
                    "article": article_title,
                    "content": content,
                    "source": source_name,
                }
            )

    return chunks


def ingest_file_bytes(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Parse, chunk, embed, and store uploaded document into ChromaDB."""
    logger.info("ingesting_document", filename=filename, size=len(file_bytes))

    raw_text = extract_text_from_bytes(file_bytes, filename)
    if not raw_text.strip():
        raise ValueError(f"تعذر استخراج أي نص من الملف: {filename}")

    chunks = chunk_legal_text(raw_text, filename)
    if not chunks:
        raise ValueError(f"لم يتم العثور على محتوى صالح للتقسيم في {filename}")

    ids = [
        f"{c.get('source', 'unknown')}_{i}_{c.get('article', '')}"
        for i, c in enumerate(chunks)
    ]
    documents = [c["content"] for c in chunks]
    metadatas: list[dict[str, Any]] = [
        {
            "source": c.get("source", ""),
            "article": c.get("article", ""),
            "category": "",
        }
        for c in chunks
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

    logger.info(
        "ingestion_complete",
        filename=filename,
        articles_indexed=len(chunks),
    )

    return {
        "filename": filename,
        "source": Path(filename).stem,
        "articles_indexed": len(chunks),
        "status": "success",
    }


def list_indexed_documents() -> list[dict[str, Any]]:
    """List distinct documents stored in ChromaDB."""
    try:
        client = get_chroma_client()
        collection = get_or_create_collection(client)
        data = collection.get()
        metadatas = data.get("metadatas") or []

        sources: dict[str, int] = {}
        for m in metadatas:
            src = m.get("source", "مستند")
            sources[src] = sources.get(src, 0) + 1

        return [
            {"source": src, "articles_count": count}
            for src, count in sources.items()
        ]
    except Exception as exc:  # Chroma may be unavailable (cold start)
        logger.error("failed_listing_docs", error=str(exc))
        return []


def delete_source(source: str) -> int:
    """Delete every chunk belonging to *source* from ChromaDB.

    Returns the number of deleted chunks (0 when the source does not exist).
    """
    client = get_chroma_client()
    collection = get_or_create_collection(client)

    existing = collection.get(where={"source": source}, include=[])
    ids = existing.get("ids") or []
    count = len(ids)
    if count:
        collection.delete(where={"source": source})

    logger.info("source_deleted", source=source, chunks=count)
    return count


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


def _article_label(match: re.Match[str]) -> str:
    """Extract a human-readable article label from a regex match."""
    if match.group(1):  # Arabic: المادة 123
        return f"المادة {match.group(1)}"
    # French: Article Premier / Article 23
    raw = match.group(0).strip()
    return raw


def chunk_by_articles(text: str) -> list[dict[str, str]]:
    """Split text into chunks by article markers (Arabic or French)."""
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
            chunks.append({"article": _article_label(match), "content": content})

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
        f"{c.get('source', 'unknown')}_{i}_{c.get('article', '')}"
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
