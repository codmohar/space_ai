"""Generate STAIR query-to-leaf-section training pairs from ingested document_sections.

Stores generated pairs in `stair_training_pairs` with:
- `reviewed = False` (pending human verification)
- Stratified `split` (`train` / `val` / `test`: 70% / 15% / 15%)
- `toc_snapshot` JSON for reproducible fine-tuning
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if (BACKEND_DIR / "app").exists():
    sys.path.insert(0, str(BACKEND_DIR))
elif Path("/app/app").exists():
    sys.path.insert(0, "/app")

from app.core.database import SessionLocal  # noqa: E402
from app.models.documents import Document, DocumentChunk, DocumentSection  # noqa: E402
from app.models.rag import StairTrainingPair  # noqa: E402
from app.services.llm.client import get_llm_client  # noqa: E402


class _GeneratedQuestions(BaseModel):
    questions: list[str] = Field(..., min_length=1, max_length=4)


def assign_stratified_split(section_id_str: str) -> str:
    """Deterministic 70/15/15 train/val/test assignment keyed by section UUID."""
    bucket = int(hashlib.sha256(section_id_str.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "val"
    return "test"


def _template_questions(mission: str, section_title: str, excerpt: str) -> list[str]:
    clean_title = section_title.strip()
    return [
        f"In the {mission} mission report, what findings are reported under {clean_title}?",
        f"What engineering details or anomalies are documented in section '{clean_title}' for {mission}?",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate STAIR leaf-section training pairs.")
    parser.add_argument("--questions-per-leaf", type=int, default=2)
    parser.add_argument("--max-leaves", type=int, default=200)
    parser.add_argument(
        "--offline-template",
        action="store_true",
        help="Generate deterministic template queries without calling Gemini API.",
    )
    parser.add_argument(
        "--export-jsonl",
        type=Path,
        default=None,
        help="Optional path to also export pairs as JSONL for Colab/Kaggle training.",
    )
    args = parser.parse_args()

    llm = None if args.offline_template else get_llm_client()
    db = SessionLocal()
    created_count = 0
    exported_rows: list[dict] = []

    try:
        docs = db.execute(select(Document)).scalars().all()
        for doc in docs:
            sections = (
                db.execute(
                    select(DocumentSection)
                    .where(DocumentSection.document_id == doc.id)
                    .order_by(DocumentSection.order_index.asc())
                )
                .scalars()
                .all()
            )
            toc_snapshot = {
                "document_id": str(doc.id),
                "doc_code": doc.doc_code,
                "mission": doc.mission,
                "sections": [
                    {
                        "id": str(s.id),
                        "parent_id": str(s.parent_id) if s.parent_id else None,
                        "title": s.title,
                        "level": s.level,
                        "is_leaf": s.is_leaf,
                        "section_path": s.section_path,
                        "page_start": s.page_start,
                        "page_end": s.page_end,
                    }
                    for s in sections
                ],
            }

            leaf_sections = [s for s in sections if s.is_leaf][: args.max_leaves]
            for sec in leaf_sections:
                chunks = (
                    db.execute(
                        select(DocumentChunk.text)
                        .where(DocumentChunk.section_id == sec.id)
                        .order_by(DocumentChunk.chunk_index.asc())
                        .limit(2)
                    )
                    .scalars()
                    .all()
                )
                excerpt = "\n".join(chunks)[:1200]
                if not excerpt.strip():
                    continue

                if args.offline_template:
                    questions = _template_questions(doc.mission, sec.title, excerpt)[
                        : args.questions_per_leaf
                    ]
                else:
                    system_prompt = (
                        "Generate realistic space-agency engineering questions that can ONLY be answered "
                        "by reading the given report section. Do not mention section numbers explicitly."
                    )
                    user_prompt = (
                        f"Mission: {doc.mission}\n"
                        f"Report: {doc.title}\n"
                        f"Section: {sec.title} (pp. {sec.page_start}-{sec.page_end})\n"
                        f"Generate {args.questions_per_leaf} concise questions.\n\n"
                        f"EXCERPT:\n{excerpt}"
                    )
                    out = llm.generate_structured(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        schema_cls=_GeneratedQuestions,
                    )
                    questions = out.questions[: args.questions_per_leaf]

                split = assign_stratified_split(str(sec.id))
                for q in questions:
                    q_clean = q.strip()
                    if not q_clean:
                        continue
                    pair = StairTrainingPair(
                        document_id=doc.id,
                        section_id=sec.id,
                        query_text=q_clean,
                        toc_snapshot=toc_snapshot,
                        split=split,
                        reviewed=False,
                    )
                    db.add(pair)
                    created_count += 1
                    exported_rows.append(
                        {
                            "document_id": str(doc.id),
                            "doc_code": doc.doc_code,
                            "target_section_id": str(sec.id),
                            "query": q_clean,
                            "split": split,
                            "reviewed": False,
                            "toc_snapshot": toc_snapshot,
                        }
                    )

        db.commit()
    finally:
        db.close()

    if args.export_jsonl:
        args.export_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.export_jsonl.open("w", encoding="utf-8") as fh:
            for row in exported_rows:
                fh.write(json.dumps(row) + "\n")
        print(f"Exported {len(exported_rows)} pairs to {args.export_jsonl}")

    print(f"Inserted {created_count} stair_training_pairs (reviewed=False).")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    raise SystemExit(main())
