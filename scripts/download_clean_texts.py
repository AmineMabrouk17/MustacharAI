"""Fetch clean Arabic text for Tunisian legal codes from 9anoun.tn mirrors.

Note on sources:
- legislation-securite.tn (DCAF) does NOT host full codes; the node IDs used
  earlier were fabricated (all 404), and its only reachable page returned site
  navigation boilerplate, not legal text.
- The official portals (legislation.tn) are unreachable (connection refused)
  and e-justice.tn uses a self-signed cert.
- 9anoun.tn hosts the full corpus in clean Unicode Arabic (enchâssement
  "الفصل" article structure). It is a private, education-focused mirror, NOT
  an official state source -- flag this before relying on it for citations.
"""

import re
import time
import unicodedata
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

DATA_DIR = Path("data/corpus_txt")
DATA_DIR.mkdir(parents=True, exist_ok=True)

LEGAL_CODES = [
    {"id": "constitution-2022", "title": "دستور الجمهورية التونسية 2022", "url": None},
    {"id": "COCArabe", "title": "مجلة الالتزامات والعقود", "url": "https://9anoun.tn/kb/codes/code-obligations-contrats"},
    {"id": "PenalArabe", "title": "المجلة الجزائية", "url": "https://9anoun.tn/kb/codes/code-penal"},
    {"id": "CommerceArabe", "title": "المجلة التجارية", "url": "https://9anoun.tn/kb/codes/code-commerce"},
    {"id": "StatutpersonnelArabe", "title": "مجلة الأحوال الشخصية", "url": "https://9anoun.tn/kb/codes/code-statut-personnel"},
    {"id": "travailArabe", "title": "مجلة الشغل", "url": "https://9anoun.tn/kb/codes/code-travail"},
    {"id": "ProcedurecivilecomArabe", "title": "مجلة المرافعات المدنية والتجارية", "url": "https://9anoun.tn/kb/codes/code-procedure-civile-commerciale"},
    {"id": "ProcedurepenaleArabe", "title": "مجلة الإجراءات الجزائية", "url": "https://9anoun.tn/kb/codes/code-procedure-penale"},
    {"id": "societeArabe", "title": "مجلة الشركات التجارية", "url": "https://9anoun.tn/kb/codes/code-societes-commerciales"},
    {"id": "EnfantArabe", "title": "مجلة حماية الطفل", "url": "https://9anoun.tn/kb/codes/code-protection-enfant"},
    {"id": "NationaliteArabe", "title": "مجلة الجنسية التونسية", "url": "https://9anoun.tn/kb/codes/code-nationalite"},
    {"id": "dtreelArabe", "title": "مجلة الحقوق العينية", "url": "https://9anoun.tn/kb/codes/code-droits-reels"},
    {"id": "ArbitrageArabe", "title": "مجلة التحكيم", "url": "https://9anoun.tn/kb/codes/code-arbitrage"},
    {"id": "DIPArabe", "title": "مجلة القانون الدولي الخاص", "url": "https://9anoun.tn/kb/codes/code-droit-international-prive"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MustacharAI/1.0",
    "Accept-Language": "ar,fr;q=0.9,en;q=0.8",
}


def extract_legal_text(html_content: str) -> str:
    """Extract article text from a 9anoun code page.

    Targets the largest text block containing the 'الفهرس' index marker and
    trims leading site-navigation boilerplate.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Prefer the div containing the article index (previously div.x878).
    candidates = []
    for div in soup.find_all("div"):
        txt = div.get_text("\n", strip=True)
        if "الفهرس" in txt and "الفصل 1" in txt and len(txt) > 5000:
            candidates.append(txt)
    candidates.sort(key=len, reverse=True)
    text = candidates[0] if candidates else soup.get_text("\n", strip=True)

    # Drop anything before the index header.
    idx = text.find("الفهرس")
    if idx != -1:
        text = text[idx + len("الفهرس"):]

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Normalize Arabic Presentation Forms (U+FB50+/U+FE70+) to standard
    # Arabic — 9anoun serves some codes using presentation-form glyphs.
    text = unicodedata.normalize("NFKC", text)
    return text.strip()


def download_all_clean_texts() -> None:
    print("Starting clean text download from 9anoun.tn ...")

    # 1. constitution-2022: reuse the already-verified clean text if present.
    existing = Path("constitution-2022.txt")
    if existing.exists() and existing.stat().st_size > 20000:
        dest = DATA_DIR / "constitution-2022.txt"
        dest.write_bytes(existing.read_bytes())
        print(f"  ✓ Copied verified clean text: {existing.name} ({existing.stat().st_size:,} bytes)")

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60.0) as client:
        for code in LEGAL_CODES:
            if code["url"] is None:
                continue

            file_path = DATA_DIR / f"{code['id']}.txt"
            if file_path.exists() and file_path.stat().st_size > 3000:
                print(f"  ✓ Already exists: {code['title']} ({file_path.name})")
                continue

            print(f"  ⬇ Downloading: {code['title']} ...")
            try:
                resp = client.get(code["url"])
                resp.raise_for_status()

                clean_text = extract_legal_text(resp.text)
                if len(clean_text) < 3000:
                    print(f"    ⚠ Warning: extracted text too short for {code['title']}")
                    continue

                file_path.write_text(clean_text, encoding="utf-8")
                print(f"    ✅ Saved {len(clean_text):,} chars to {file_path.name}")
            except Exception as e:
                print(f"    ❌ Failed {code['title']}: {e}")

            time.sleep(1.0)

    print(f"\nDone! Clean text files saved into: {DATA_DIR.resolve()}")


if __name__ == "__main__":
    download_all_clean_texts()