"""CLI seed/ingestion script for MISSIONWISE AI.

Reads data/raw_documents/manifest.json (with required source_url & licence)
and runs the shared backend ingestion pipeline against PostgreSQL + pgvector.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Support running both from repo root (./scripts/...) and inside backend container (/scripts/...)
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if (BACKEND_DIR / "app").exists():
    sys.path.insert(0, str(BACKEND_DIR))
elif Path("/app/app").exists():
    sys.path.insert(0, "/app")

from app.core.database import SessionLocal  # noqa: E402
from app.services.ingestion.pipeline import IngestionPipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest mission PDFs from a manifest JSON file.")
    default_manifest = (
        Path("/data/raw_documents/manifest.json")
        if Path("/data/raw_documents/manifest.json").exists()
        else REPO_ROOT / "data" / "raw_documents" / "manifest.json"
    )
    parser.add_argument("--manifest", type=Path, default=default_manifest, help="Path to manifest.json")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_dir = args.manifest.parent
    pipeline = IngestionPipeline()

    db = SessionLocal()
    try:
        for entry in entries:
            pdf_path = manifest_dir / entry["filename"]
            if not pdf_path.exists():
                print(f"[ERROR] Missing PDF file: {pdf_path}", file=sys.stderr)
                return 1

            result = pipeline.ingest_file(
                db=db,
                file_path=pdf_path,
                doc_code=entry["doc_code"],
                title=entry["title"],
                source_url=entry["source_url"],
                licence=entry["licence"],
                org=entry.get("org", "NASA"),
                mission=entry.get("mission", "Unknown"),
                version=entry.get("version", "1.0"),
            )
            print(
                f"[{result.status.upper()}] {entry['doc_code']} | "
                f"pages={result.page_count} sections={result.section_count} chunks={result.chunk_count} "
                f"ocr_pages={result.ocr_pages}"
            )
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    raise SystemExit(main())
