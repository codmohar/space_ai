"""Download and verify the 3 curated public mission reports listed in manifest.json."""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw_documents"
MANIFEST_PATH = RAW_DIR / "manifest.json"


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MISSIONWISE-AI/1.0 (Space Mission Research Tool)"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"Downloaded content from {url} is not a valid PDF (missing %PDF- magic bytes)")
    dest.write_bytes(data)


def main() -> int:
    if not MANIFEST_PATH.exists():
        print(f"Manifest not found: {MANIFEST_PATH}", file=sys.stderr)
        return 1

    entries = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in entries:
        dest = RAW_DIR / entry["filename"]
        if dest.exists() and dest.read_bytes()[:5] == b"%PDF-":
            sha = hashlib.sha256(dest.read_bytes()).hexdigest()
            print(f"[SKIP] {entry['doc_code']} already present ({dest.stat().st_size:,} bytes, sha256={sha[:12]}...)")
            continue

        urls = [entry["source_url"], *entry.get("fallback_urls", [])]
        downloaded = False
        for url in urls:
            try:
                print(f"[GET ] {entry['doc_code']} <- {url}")
                _download(url, dest)
                sha = hashlib.sha256(dest.read_bytes()).hexdigest()
                print(f"[OK  ] Saved {dest.name} ({dest.stat().st_size:,} bytes, sha256={sha[:12]}...)")
                downloaded = True
                break
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] Failed {url}: {exc}", file=sys.stderr)

        if not downloaded:
            print(f"[FAIL] Could not download {entry['doc_code']}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
