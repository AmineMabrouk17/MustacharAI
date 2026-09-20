import re
from pathlib import Path
import fitz  # PyMuPDF


PDF_PATH = "constitution-2022.pdf"

# Matches Arabic legal structural markers:
# - الفصول: الفصل 1 / الفصل الأول / الفصل الحادي والعشرون
# - المواد: المادة 1 / مادة 2
# - الأبواب / الأقسام
ARTICLE_PATTERN = re.compile(
    r"(?:^|\n)\s*(الفصل|المادة|مادة)\s+([0-9]+|الأول|الأولى|[\u0621-\u064A\s]+?)(?:\s*[:.\-–—]|\n)",
    re.UNICODE | re.MULTILINE,
)


def extract_arabic_text(pdf_path: str | Path) -> str:
    """Extract clean text page-by-page using PyMuPDF."""
    doc = fitz.open(str(pdf_path))
    pages_text = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # "text" mode preserves logical reading order
        text = page.get_text("text")
        if text.strip():
            pages_text.append(text.strip())

    full_text = "\n\n".join(pages_text)

    # Normalize excessive spaces and common ligature artifacts
    full_text = re.sub(r"[ \t]+", " ", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)

    return full_text


def chunk_arabic_legal_doc(text: str) -> list[dict]:
    """
    Split legal text cleanly by Articles (الفصول / المواد).
    Keeps the preamble (توطئة / ديباجة) as a distinct chunk.
    """
    matches = list(ARTICLE_PATTERN.finditer(text))

    if not matches:
        print("[WARNING] No articles detected with regex. Falling back to paragraph chunking.")
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
        return [{"article": f"فقرة {i+1}", "content": p} for i, p in enumerate(paragraphs)]

    chunks = []

    # 1. Extract Preamble / Introduction if present
    first_match_start = matches[0].start()
    preamble = text[:first_match_start].strip()
    if preamble:
        chunks.append({
            "article": "توطئة / مقدمة",
            "content": preamble
        })

    # 2. Extract each article cleanly
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        article_type = match.group(1).strip()
        article_num = match.group(2).strip().replace("\n", " ")
        label = f"{article_type} {article_num}"

        content = text[start:end].strip()
        if content:
            chunks.append({
                "article": label,
                "content": content
            })

    return chunks


def inspect_chunks():
    print(f"--> Reading {PDF_PATH} ...")
    raw_text = extract_arabic_text(PDF_PATH)

    print(f"--> Extracted {len(raw_text)} total characters.")
    print("--> Splitting into legal chunks...")
    chunks = chunk_arabic_legal_doc(raw_text)

    print(f"\n✅ Total Chunks Generated: {len(chunks)}\n")
    print("=" * 60)

    # Preview the first 3 chunks to verify Arabic direction and readability
    for i, chunk in enumerate(chunks[:3]):
        print(f"\n[CHUNK {i+1}] Title: {chunk['article']}")
        print(f"Content Preview (first 250 chars):\n{chunk['content'][:250]}...")
        print("-" * 60)

    # Export all chunks to a text file for complete visual inspection
    out_file = Path("inspected_chunks.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(f"=== {c['article']} ===\n")
            f.write(f"{c['content']}\n\n")

    print(f"--> All chunks saved to '{out_file.name}' for inspection.")


if __name__ == "__main__":
    inspect_chunks()