"""CLI script to index mission_incidents, mission_entities, and mission_entity_relations."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if (BACKEND_DIR / "app").exists():
    sys.path.insert(0, str(BACKEND_DIR))
elif Path("/app/app").exists():
    sys.path.insert(0, "/app")

from app.core.database import SessionLocal  # noqa: E402
from app.services.incidents.indexer import IncidentKGIndexer  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        indexer = IncidentKGIndexer()
        results = indexer.index_all_documents(db=db, force_rebuild=True)
        for r in results:
            print(
                f"[INDEXED] {r.doc_code} | incidents={r.incidents_indexed} "
                f"(verified={r.verified_incidents}) entities={r.entities_created} relations={r.relations_created}"
            )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    raise SystemExit(main())
