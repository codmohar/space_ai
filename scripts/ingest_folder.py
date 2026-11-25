"""Bulk folder ingestion utility for MISSIONWISE AI.

Idempotently scans a directory (default: data/raw_documents) for PDF files,
skips already indexed files by SHA-256 hash, and ingests new documents
through the centralized UniversalDocumentParser + IngestionPipeline.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.core.database import SessionLocal
from app.core.security import compute_sha256
from app.models.documents import Document
from app.services.ingestion.job_queue import get_job_manager
from sqlalchemy import select


def ingest_folder(folder_path: Path, mission: str | None = None, org: str | None = None) -> int:
    if not folder_path.exists() or not folder_path.is_dir():
        print(f"[!] Target directory does not exist: {folder_path}")
        return 1

    files = [
        f for f in folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in (".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".csv", ".xml")
    ]
    if not files:
        print(f"[-] No supported document files found in {folder_path}")
        return 0

    print(f"[*] Found {len(files)} files in {folder_path}. Checking against indexed hashes...")

    db = SessionLocal()
    job_mgr = get_job_manager()
    newly_queued = 0

    try:
        # Load existing SHA-256 hashes
        existing_hashes = set(db.execute(select(Document.sha256_hash)).scalars().all())

        for file_path in files:
            data = file_path.read_bytes()
            file_hash = compute_sha256(data)
            filename = file_path.name

            if file_hash in existing_hashes:
                doc = db.execute(select(Document).where(Document.sha256_hash == file_hash)).scalar_one_or_none()
                doc_code = doc.doc_code if doc else "UNKNOWN"
                print(f"  [SKIP] {filename} is already indexed as {doc_code} (hash: {file_hash[:10]}...)")
                continue

            doc_title = file_path.stem.replace("_", " ").replace("-", " ").title()
            inferred_mission = mission or "Curated Aerospace Mission"
            inferred_org = org or "NASA/NTRS"

            print(f"  [QUEUE] Ingesting {filename} ({len(data)} bytes)...")
            job_id = job_mgr.submit_job(
                filename=filename,
                raw_bytes=data,
                title=doc_title,
                organization=inferred_org,
                mission=inferred_mission,
                source_url="uploaded, no public URL",
                licence="Public Domain / NASA Technical Report",
                classification="public",
            )
            print(f"    -> Job queued: {job_id}")
            newly_queued += 1

    finally:
        db.close()

    print(f"[+] Scan complete: {newly_queued} new files submitted to ingestion queue.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotently ingest folder of mission documents into MISSIONWISE AI.")
    parser.add_argument("folder", nargs="?", default="./data/raw_documents", help="Folder containing documents")
    parser.add_argument("--mission", help="Mission name override")
    parser.add_argument("--org", help="Organization name override")
    args = parser.parse_args()

    return ingest_folder(Path(args.folder), mission=args.mission, org=args.org)


if __name__ == "__main__":
    sys.exit(main())
