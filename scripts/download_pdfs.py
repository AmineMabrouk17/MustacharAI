#!/usr/bin/env python3
"""Download Tunisian legal code PDFs into data/raw_pdfs/."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import unquote

import httpx

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_pdfs"

PDF_SOURCES: list[dict[str, str]] = [
    # Code des Obligations et des Contrats
    {
        "name": "code_des_obligations_et_des_contrats.pdf",
        "url": "https://www.diwan.tn/fr/document/card/537e9b79-3575-4394-93fd-752966b85c77",
        "category": "قانون الالتزامات والعقود",
    },
    # Code Pénal
    {
        "name": "code_penal.pdf",
        "url": "https://cdm21069.contentdm.oclc.org/digital/api/collection/ppl1/id/327120/download",
        "category": "القانون الجنائي",
    },
    {
        "name": "code_penal_natlex.pdf",
        "url": "https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/33572/TUN-33572.pdf",
        "category": "القانون الجنائي",
    },
    # Code du Statut Personnel
    {
        "name": "code_du_statut_personnel.pdf",
        "url": "http://jafbase.fr/docMaghreb/TunisieStatutpersonnel.PDF",
        "category": "قانون الحالة الشخصية",
    },
    # Code du Travail
    {
        "name": "code_du_travail_2020.pdf",
        "url": "http://chaexpert.com/documents/Code%20Travail%20Tunisie%202020.pdf",
        "category": "قانون الشغل",
    },
    # Code de Commerce
    {
        "name": "code_de_commerce.pdf",
        "url": "http://www.bna.tn/documents/code_de_commerce.pdf",
        "category": "قانون التجارة",
    },
    # Code des Droits Réels
    {
        "name": "code_des_droits_reels.pdf",
        "url": "https://www.pist.tn/jort/1965/1965F/Jo01065.pdf",
        "category": "قانون الحقوق العينية",
    },
    # Code de Procédure Pénale
    {
        "name": "code_de_procedure_penale.pdf",
        "url": "https://www.africa-laws.org/Tunisia/criminal%20law/Code%20de%20proc%C3%A9dure%20p%C3%A9nale.pdf",
        "category": "قانون الإجراءات الجرمية",
    },
    # Code des Obligations et des Contrats (BNA backup)
    {
        "name": "code_des_obligations_et_des_contrats_bna.pdf",
        "url": "http://www.bna.tn/documents/Code_des_obligations_et_des_contrats.pdf",
        "category": "قانون الالتزامات والعقود",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) MustacharAI/1.0"
}


def download_pdf(entry: dict[str, str], dest_dir: Path) -> Path | None:
    """Download a single PDF. Returns path on success, None on failure."""
    dest = dest_dir / entry["name"]
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  [skip] {entry['name']} already exists ({dest.stat().st_size} bytes)")
        return dest

    print(f"  [download] {entry['name']} ...")
    try:
        with httpx.Client(
            follow_redirects=True, timeout=60, headers=HEADERS
        ) as client:
            resp = client.get(entry["url"])
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "pdf" not in content_type and "octet-stream" not in content_type:
                # Some servers don't set content-type properly; check magic bytes
                if not resp.content[:4] == b"%PDF":
                    print(
                        f"  [warn] {entry['name']}: response is not PDF "
                        f"(content-type: {content_type}), saving anyway"
                    )

            dest.write_bytes(resp.content)
            print(f"  [ok] {entry['name']} ({len(resp.content)} bytes)")
            return dest
    except Exception as exc:
        print(f"  [FAIL] {entry['name']}: {exc}")
        return None


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {len(PDF_SOURCES)} PDFs to {RAW_DIR}\n")

    succeeded: list[Path] = []
    failed: list[str] = []

    for entry in PDF_SOURCES:
        result = download_pdf(entry, RAW_DIR)
        if result:
            succeeded.append(result)
        else:
            failed.append(entry["name"])
        time.sleep(1)  # polite delay

    print(f"\n--- Summary ---")
    print(f"Downloaded: {len(succeeded)}")
    print(f"Failed:     {len(failed)}")
    if failed:
        print(f"Failed files: {', '.join(failed)}")

    # Write a manifest so ingestion can use categories
    manifest_path = RAW_DIR / "manifest.csv"
    with manifest_path.open("w") as f:
        f.write("filename,category\n")
        for entry in PDF_SOURCES:
            if (RAW_DIR / entry["name"]).exists():
                f.write(f"{entry['name']},{entry['category']}\n")
    print(f"\nManifest written to {manifest_path}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
