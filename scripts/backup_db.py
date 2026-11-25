"""Database and Storage Backup Utility for MISSIONWISE AI.

Dumps PostgreSQL database (including pgvector embeddings and full-text indexes)
and archives local document storage into a compressed timestamped tarball.
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup MISSIONWISE AI PostgreSQL database and files.")
    parser.add_argument("--out-dir", default="./backups", help="Directory where backup tarball is saved")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL connection string")
    parser.add_argument("--storage-dir", default=os.getenv("STORAGE_DIR", "./data/storage"), help="Path to document storage")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    temp_stage = out_dir / f"stage_{timestamp}"
    temp_stage.mkdir(parents=True, exist_ok=True)

    archive_path = out_dir / f"missionwise_backup_{timestamp}.tar.gz"

    print(f"[*] Starting MISSIONWISE backup to {archive_path}...")

    # 1. Dump database via pg_dump if db_url provided
    db_dump_file = temp_stage / "database.sql"
    if args.db_url:
        parsed = urlparse(args.db_url)
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password

        host = parsed.hostname or "localhost"
        port = str(parsed.port or 5432)
        user = parsed.username or "postgres"
        dbname = parsed.path.lstrip("/") or "missionwise"

        cmd = [
            "pg_dump",
            "-h", host,
            "-p", port,
            "-U", user,
            "-F", "c",  # Custom archive format for pg_restore
            "-b",        # Include blobs
            "-v",
            "-f", str(temp_stage / "database.dump"),
            dbname,
        ]
        print(f"[*] Exporting database {dbname} on {host}:{port}...")
        try:
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[!] pg_dump failed: {res.stderr}. Writing fallback warning note.")
                (temp_stage / "pg_dump_error.txt").write_text(res.stderr)
            else:
                print("[+] Database dump created successfully.")
        except FileNotFoundError:
            print("[!] pg_dump CLI tool not found in PATH. Skipping binary pg_dump.")
            (temp_stage / "README_DUMP.txt").write_text(
                "pg_dump binary was not available in host environment at backup time.\n"
                f"Source connection: {args.db_url}\n"
            )

    # 2. Archive storage directory
    storage_path = Path(args.storage_dir)
    if storage_path.exists() and any(storage_path.iterdir()):
        print(f"[*] Copying storage files from {storage_path}...")
        dest_storage = temp_stage / "storage"
        shutil.copytree(storage_path, dest_storage, dirs_exist_ok=True)
        print("[+] Storage files staged.")
    else:
        print("[-] Storage directory empty or missing.")

    # 3. Create compressed archive
    print(f"[*] Compressing backup archive: {archive_path}...")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(temp_stage, arcname="backup")

    # Cleanup staging directory
    shutil.rmtree(temp_stage, ignore_errors=True)
    print(f"[+] Backup complete: {archive_path} ({archive_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
