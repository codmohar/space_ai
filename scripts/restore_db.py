"""Database and Storage Restore Utility for MISSIONWISE AI.

Restores PostgreSQL database and extracts document storage from a backup tarball.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore MISSIONWISE AI PostgreSQL database and files.")
    parser.add_argument("archive", help="Path to missionwise_backup_*.tar.gz archive")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL connection string")
    parser.add_argument("--storage-dir", default=os.getenv("STORAGE_DIR", "./data/storage"), help="Path to document storage")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    if not archive_path.exists():
        print(f"[!] Archive file not found: {archive_path}")
        return 1

    stage_dir = archive_path.parent / f"restore_stage_{archive_path.stem}"
    stage_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Extracting {archive_path} to {stage_dir}...")
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(stage_dir)

    backup_content = stage_dir / "backup"
    if not backup_content.exists():
        backup_content = stage_dir

    # 1. Restore storage files
    staged_storage = backup_content / "storage"
    target_storage = Path(args.storage_dir)
    if staged_storage.exists():
        print(f"[*] Restoring documents to {target_storage}...")
        target_storage.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged_storage, target_storage, dirs_exist_ok=True)
        print("[+] Storage restored.")

    # 2. Restore database
    db_dump = backup_content / "database.dump"
    if db_dump.exists() and args.db_url:
        parsed = urlparse(args.db_url)
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password

        host = parsed.hostname or "localhost"
        port = str(parsed.port or 5432)
        user = parsed.username or "postgres"
        dbname = parsed.path.lstrip("/") or "missionwise"

        cmd = [
            "pg_restore",
            "-h", host,
            "-p", port,
            "-U", user,
            "-d", dbname,
            "-c",       # Clean/drop database objects before recreating
            "-v",
            str(db_dump),
        ]
        print(f"[*] Restoring database {dbname} from {db_dump}...")
        try:
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            print(f"[+] pg_restore output: {res.stdout or res.stderr}")
        except FileNotFoundError:
            print("[!] pg_restore CLI tool not found in PATH.")

    shutil.rmtree(stage_dir, ignore_errors=True)
    print("[+] Restore operation finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
