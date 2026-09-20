import re
from pathlib import Path

# Set this to your clean source file (either .txt or clean .pdf)
SOURCE_PATH = Path("constitution-2022.txt")

# Regex to accurately match all articles of the Tunisian Constitution (الفصول)
ARTICLE_PATTERN = re.compile(
    r"(?:^|\n)\s*(الفصل\s+(?:\d+|الأول|الأولى|[\u0621-\u064A\s]+?))(?:\s*[:.\-–—]|\n)",
    re.UNICODE,
)


def load_source_text(file_path: Path) -> str:
    """Load text cleanly from TXT or PDF."""
    if file_path.suffix.lower() == ".txt":
        return file_path.read_text(encoding="utf-8")

    elif file_path.suffix.lower() == ".pdf":
        import fitz
        doc = fitz.open(str(file_path))
        return "\n\n".join(page.get_text("text").strip() for page in doc if page.get_text("text").strip())

    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")


def chunk_by_chapters_and_articles(text: str) -> list[dict]:
    """
    Splits the Tunisian Constitution cleanly by its legal structure:
    - Preamble (التوطئة)
    - Articles (الفصول)
    """
    # Normalize spaces and newlines
    normalized_text = re.sub(r"\r\n", "\n", text)
    normalized_text = re.sub(r"[ \t]+", " ", normalized_text)

    matches = list(ARTICLE_PATTERN.finditer(normalized_text))

    if not matches:
        print("⚠️ No articles detected by regex! Check the text formatting.")
        return []

    chunks = []

    # 1. Preamble (التوطئة)
    preamble = normalized_text[:matches[0].start()].strip()
    if preamble:
        chunks.append({
            "article": "التوطئة",
            "content": preamble
        })

    # 2. Extract every 'الفصل'
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(normalized_text)

        article_title = match.group(1).strip().replace("\n", " ")
        content = normalized_text[start:end].strip()

        chunks.append({
            "article": article_title,
            "content": content
        })

    return chunks


def run():
    if not SOURCE_PATH.exists():
        print(f"❌ File {SOURCE_PATH} not found.")
        print("Please place the clean text version as constitution-2022.txt.")
        return

    text = load_source_text(SOURCE_PATH)
    chunks = chunk_by_chapters_and_articles(text)

    print(f"✅ Successfully chunked {len(chunks)} sections/articles!")

    # Verify the first few chunks
    for chunk in chunks[:3]:
        print("\n----------------------------------------")
        print(f"Title: {chunk['article']}")
        print(f"Preview: {chunk['content'][:150]}...")

    # Save output for inspection
    with open("inspected_chunks.txt", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(f"=== {c['article']} ===\n{c['content']}\n\n")

    print("\n✅ Saved chunks to 'inspected_chunks.txt'. Check it now!")


if __name__ == "__main__":
    run()