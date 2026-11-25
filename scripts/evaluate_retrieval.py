"""Evaluate retrieval strategies across data/evaluation/questions.jsonl.

Compares:
- bm25 (lexical chunk retrieval)
- dense (pgvector HNSW dense retrieval)
- hybrid (BM25 + dense + RRF + cross-encoder reranker, L1 pass-through)
- bm25_toc (BM25-over-ToC section selector + hybrid)
- stair_l2 (STAIR-inspired ToC+query -> validated leaf IDs + hybrid)
- stair_l3 (if trained LoRA adapter exists at STAIR_LORA_ADAPTER_PATH)

Outputs measured JSON to data/evaluation/retrieval_results.json for GET /api/eval/results.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi
from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if (BACKEND_DIR / "app").exists():
    sys.path.insert(0, str(BACKEND_DIR))
elif Path("/app/app").exists():
    sys.path.insert(0, "/app")

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.documents import Document, DocumentChunk, DocumentEmbedding, DocumentSection  # noqa: E402
from app.services.retrieval.embeddings import get_embedding_service  # noqa: E402
from app.services.retrieval.hybrid import HybridRetriever  # noqa: E402
from app.services.retrieval.section_selector import (  # noqa: E402
    BM25ToCSectionSelector,
    FineTunedSTAIRSectionSelector,
    L1PassThroughSectionSelector,
    STAIRInspiredSectionSelector,
)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*", text.lower())


def is_chunk_relevant(chunk_text: str, doc_code: str, expected_doc: str | None, expected_keywords: list[str]) -> bool:
    if expected_doc and doc_code != expected_doc:
        return False
    if not expected_keywords:
        return False
    lower = chunk_text.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in lower)
    return hits >= max(1, min(2, len(expected_keywords)))


def compute_query_metrics(relevances: list[bool]) -> dict[str, float]:
    """Compute Recall@1, Recall@3, Recall@5, MRR, and nDCG@5 from ranked binary relevance list."""
    r1 = 1.0 if any(relevances[:1]) else 0.0
    r3 = 1.0 if any(relevances[:3]) else 0.0
    r5 = 1.0 if any(relevances[:5]) else 0.0

    mrr = 0.0
    for idx, rel in enumerate(relevances, start=1):
        if rel:
            mrr = 1.0 / idx
            break

    dcg = sum((1.0 / math.log2(idx + 1)) for idx, rel in enumerate(relevances[:5], start=1) if rel)
    ideal_hits = min(5, sum(1 for rel in relevances if rel))
    idcg = sum((1.0 / math.log2(idx + 1)) for idx in range(1, ideal_hits + 1))
    ndcg5 = (dcg / idcg) if idcg > 0 else 0.0

    return {
        "recall_at_1": r1,
        "recall_at_3": r3,
        "recall_at_5": r5,
        "mrr": mrr,
        "ndcg_at_5": ndcg5,
    }


def aggregate_method_metrics(
    method_name: str,
    stair_level: str,
    per_query: list[dict[str, float]],
    latencies_ms: list[float],
    invalid_ids: int = 0,
    proposed_ids: int = 0,
) -> dict[str, Any]:
    n = max(1, len(per_query))
    sorted_lat = sorted(latencies_ms) if latencies_ms else [0.0]
    p95_idx = min(len(sorted_lat) - 1, int(0.95 * len(sorted_lat)))

    return {
        "method": method_name,
        "stair_level": stair_level,
        "evaluated_questions": len(per_query),
        "recall_at_1": round(sum(m["recall_at_1"] for m in per_query) / n, 4),
        "recall_at_3": round(sum(m["recall_at_3"] for m in per_query) / n, 4),
        "recall_at_5": round(sum(m["recall_at_5"] for m in per_query) / n, 4),
        "mrr": round(sum(m["mrr"] for m in per_query) / n, 4),
        "ndcg_at_5": round(sum(m["ndcg_at_5"] for m in per_query) / n, 4),
        "invalid_section_rate": round(invalid_ids / proposed_ids, 4) if proposed_ids > 0 else 0.0,
        "avg_latency_ms": round(sum(latencies_ms) / max(1, len(latencies_ms)), 2),
        "p95_latency_ms": round(sorted_lat[p95_idx], 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run retrieval benchmark on data/evaluation/questions.jsonl")
    parser.add_argument(
        "--questions",
        type=Path,
        default=REPO_ROOT / "data" / "evaluation" / "questions.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data" / "evaluation" / "retrieval_results.json",
    )
    parser.add_argument("--include-stair-l2", action="store_true", help="Include LLM-based STAIR L2 evaluation")
    args = parser.parse_args()

    questions = [
        json.loads(line)
        for line in args.questions.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    answerable_qs = [q for q in questions if q.get("answerable", True)]
    settings = get_settings()

    db = SessionLocal()
    try:
        # Preload chunk corpus for BM25 baseline
        all_chunks = db.execute(
            select(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id)
        ).all()
        if not all_chunks:
            print("No ingested chunks in database. Seed documents before evaluating.", file=sys.stderr)
            return 1

        tokenized_corpus = [_tokenize(c.text) for c, _d in all_chunks]
        bm25_index = BM25Okapi(tokenized_corpus)
        embedder = get_embedding_service()

        method_results: list[dict[str, Any]] = []

        # 1. BM25 baseline
        bm25_metrics, bm25_lats = [], []
        for q in answerable_qs:
            t0 = time.perf_counter()
            scores = bm25_index.get_scores(_tokenize(q["query"]))
            ranked_idx = sorted(range(len(all_chunks)), key=lambda i: float(scores[i]), reverse=True)[:5]
            bm25_lats.append((time.perf_counter() - t0) * 1000.0)
            rels = [
                is_chunk_relevant(all_chunks[i][0].text, all_chunks[i][1].doc_code, q.get("doc_code"), q.get("expected_keywords", []))
                for i in ranked_idx
            ]
            bm25_metrics.append(compute_query_metrics(rels))
        method_results.append(aggregate_method_metrics("bm25", "Baseline", bm25_metrics, bm25_lats))

        # 2. Dense vector baseline
        dense_metrics, dense_lats = [], []
        for q in answerable_qs:
            t0 = time.perf_counter()
            q_vec = embedder.embed_query(q["query"])
            dist = DocumentEmbedding.embedding.cosine_distance(q_vec)
            rows = db.execute(
                select(DocumentChunk, Document)
                .join(DocumentEmbedding, DocumentEmbedding.chunk_id == DocumentChunk.id)
                .join(Document, Document.id == DocumentChunk.document_id)
                .order_by(dist.asc())
                .limit(5)
            ).all()
            dense_lats.append((time.perf_counter() - t0) * 1000.0)
            rels = [
                is_chunk_relevant(c.text, d.doc_code, q.get("doc_code"), q.get("expected_keywords", []))
                for c, d in rows
            ]
            dense_metrics.append(compute_query_metrics(rels))
        method_results.append(aggregate_method_metrics("dense", "Baseline", dense_metrics, dense_lats))

        # 3. Hybrid + Rerank (L1 Pass-Through)
        hybrid_ret = HybridRetriever(section_selector=L1PassThroughSectionSelector())
        hyb_metrics, hyb_lats = [], []
        for q in answerable_qs:
            cands, tel = hybrid_ret.search(db, q["query"], top_k=5)
            hyb_lats.append(tel["total_ms"])
            rels = [
                is_chunk_relevant(c.text, c.doc_code, q.get("doc_code"), q.get("expected_keywords", []))
                for c in cands
            ]
            hyb_metrics.append(compute_query_metrics(rels))
        method_results.append(aggregate_method_metrics("hybrid", "L1", hyb_metrics, hyb_lats))

        # 4. BM25-over-ToC + Hybrid
        bm25_toc_ret = HybridRetriever(section_selector=BM25ToCSectionSelector())
        bt_metrics, bt_lats = [], []
        for q in answerable_qs:
            cands, tel = bm25_toc_ret.search(db, q["query"], top_k=5)
            bt_lats.append(tel["total_ms"])
            rels = [
                is_chunk_relevant(c.text, c.doc_code, q.get("doc_code"), q.get("expected_keywords", []))
                for c in cands
            ]
            bt_metrics.append(compute_query_metrics(rels))
        method_results.append(aggregate_method_metrics("bm25_toc", "L1-BM25", bt_metrics, bt_lats))

        # 5. STAIR-Inspired L2 (when --include-stair-l2 or GEMINI_API_KEY configured)
        if args.include_stair_l2 or settings.gemini_api_key:
            stair_l2_sel = STAIRInspiredSectionSelector()
            stair_ret = HybridRetriever(section_selector=stair_l2_sel)
            l2_metrics, l2_lats = [], []
            invalid_sum, proposed_sum = 0, 0
            for q in answerable_qs:
                sel_res = stair_l2_sel.select(db, q["query"], top_k_sections=settings.stair_top_k_sections)
                invalid_sum += sel_res.invalid_ids_count
                proposed_sum += sel_res.total_proposed_ids
                cands, tel = stair_ret.search(db, q["query"], top_k=5)
                l2_lats.append(tel["total_ms"])
                rels = [
                    is_chunk_relevant(c.text, c.doc_code, q.get("doc_code"), q.get("expected_keywords", []))
                    for c in cands
                ]
                l2_metrics.append(compute_query_metrics(rels))
            method_results.append(
                aggregate_method_metrics(
                    "stair_l2", "L2", l2_metrics, l2_lats, invalid_ids=invalid_sum, proposed_ids=proposed_sum
                )
            )

        # 6. STAIR L3 Fine-tuned (only if trained LoRA adapter exists)
        l3_sel = FineTunedSTAIRSectionSelector()
        if l3_sel.is_trained_model_available():
            l3_ret = HybridRetriever(section_selector=l3_sel)
            l3_metrics, l3_lats = [], []
            invalid_sum, proposed_sum = 0, 0
            for q in answerable_qs:
                sel_res = l3_sel.select(db, q["query"], top_k_sections=settings.stair_top_k_sections)
                invalid_sum += sel_res.invalid_ids_count
                proposed_sum += sel_res.total_proposed_ids
                cands, tel = l3_ret.search(db, q["query"], top_k=5)
                l3_lats.append(tel["total_ms"])
                rels = [
                    is_chunk_relevant(c.text, c.doc_code, q.get("doc_code"), q.get("expected_keywords", []))
                    for c in cands
                ]
                l3_metrics.append(compute_query_metrics(rels))
            method_results.append(
                aggregate_method_metrics(
                    "stair_l3", "L3", l3_metrics, l3_lats, invalid_ids=invalid_sum, proposed_ids=proposed_sum
                )
            )

        payload = {
            "status": "evaluated",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_path": str(args.questions.name),
            "total_questions": len(questions),
            "answerable_questions": len(answerable_qs),
            "unanswerable_questions": len(questions) - len(answerable_qs),
            "methods": method_results,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote measured evaluation results to {args.output}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    raise SystemExit(main())
