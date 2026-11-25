"""Hybrid retrieval: pgvector HNSW dense + BM25 lexical + RRF + Cross-Encoder reranker."""

from __future__ import annotations

import math
import re
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.documents import (
    Document,
    DocumentChunk,
    DocumentEmbedding,
    DocumentSection,
)
from app.services.retrieval.embeddings import get_embedding_service
from app.services.retrieval.section_selector import (
    SectionSelector,
    build_section_selector,
)


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*", text.lower())


@dataclass
class RetrievedCandidate:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    doc_code: str
    document_title: str
    source_url: str
    licence: str
    mission: str
    section_id: Optional[uuid.UUID]
    section_title: str
    section_path: str
    page_number: int
    text: str
    bbox_json: list[dict[str, Any]]
    dense_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0


class CrossEncoderReranker:
    def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
        self.model_name = model_name
        self._model = CrossEncoder(model_name, cache_folder=cache_dir)

    def score_pairs(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, p) for p in passages]
        raw_scores = self._model.predict(pairs, show_progress_bar=False)
        return [round(_sigmoid(float(s)), 4) for s in raw_scores]


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    settings = get_settings()
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    return CrossEncoderReranker(
        model_name=settings.reranker_model,
        cache_dir=str(settings.model_cache_dir),
    )


class HybridRetriever:
    def __init__(self, section_selector: SectionSelector | None = None) -> None:
        self.settings = get_settings()
        self.section_selector = section_selector or build_section_selector()

    def search(
        self,
        db: Session,
        query: str,
        mission: Optional[str] = None,
        document_ids: Optional[list[uuid.UUID]] = None,
        top_k: Optional[int] = None,
        allowed_classifications: Optional[list[str]] = None,
    ) -> tuple[list[RetrievedCandidate], dict[str, Any]]:
        t0 = time.perf_counter()
        final_k = top_k or self.settings.retrieval_top_k_rerank

        # Resolve mission filter -> document_ids if mission provided
        scoped_doc_ids = document_ids
        if mission and not scoped_doc_ids:
            mission_docs = db.execute(
                select(Document.id).where(func.lower(Document.mission) == mission.strip().lower())
            ).scalars().all()
            if mission_docs:
                scoped_doc_ids = list(mission_docs)

        selection_res = self.section_selector.select(
            db=db,
            query=query,
            document_ids=scoped_doc_ids,
            top_k_sections=self.settings.stair_top_k_sections,
            allowed_classifications=allowed_classifications,
        )
        selected_section_ids = selection_res.selected_section_ids

        # 1. Dense vector search: Leaf sections + Global safety net pass
        t_dense_start = time.perf_counter()
        embedder = get_embedding_service()
        query_vec = embedder.embed_query(query)

        distance_expr = DocumentEmbedding.embedding.cosine_distance(query_vec)
        base_dense = (
            select(
                DocumentChunk,
                Document,
                DocumentSection,
                (1.0 - distance_expr).label("dense_score"),
            )
            .join(DocumentEmbedding, DocumentEmbedding.chunk_id == DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .outerjoin(DocumentSection, DocumentSection.id == DocumentChunk.section_id)
            .order_by(distance_expr.asc())
        )
        if scoped_doc_ids:
            base_dense = base_dense.where(DocumentChunk.document_id.in_(scoped_doc_ids))
        if allowed_classifications:
            base_dense = base_dense.where(Document.classification.in_(allowed_classifications))

        # (a) Pass 1: In-section dense search
        dense_rows_section = []
        if selected_section_ids:
            dense_stmt_sec = base_dense.where(DocumentChunk.section_id.in_(selected_section_ids)).limit(
                self.settings.retrieval_top_k_dense
            )
            dense_rows_section = list(db.execute(dense_stmt_sec).all())

        # (b) Pass 2: Global safety net dense search (ensures no valid answer is hidden by section misclassification)
        dense_stmt_global = base_dense.limit(self.settings.retrieval_top_k_dense)
        dense_rows_global = list(db.execute(dense_stmt_global).all())

        # Merge dense rows preserving highest score
        seen_dense_chunks: set[uuid.UUID] = set()
        dense_rows = []
        for r in (dense_rows_section + dense_rows_global):
            chk_id = r[0].id
            if chk_id not in seen_dense_chunks:
                seen_dense_chunks.add(chk_id)
                dense_rows.append(r)
        dense_rows = dense_rows[: self.settings.retrieval_top_k_dense * 2]
        dense_ms = (time.perf_counter() - t_dense_start) * 1000.0

        # 2. BM25 lexical search: In-section + Global safety net pass
        t_bm25_start = time.perf_counter()
        base_bm25_pool = (
            select(DocumentChunk, Document, DocumentSection)
            .join(Document, Document.id == DocumentChunk.document_id)
            .outerjoin(DocumentSection, DocumentSection.id == DocumentChunk.section_id)
        )
        if scoped_doc_ids:
            base_bm25_pool = base_bm25_pool.where(DocumentChunk.document_id.in_(scoped_doc_ids))
        if allowed_classifications:
            base_bm25_pool = base_bm25_pool.where(Document.classification.in_(allowed_classifications))

        fts_query = func.websearch_to_tsquery("english", query)
        fts_rows_sec = []
        if selected_section_ids:
            fts_stmt_sec = base_bm25_pool.where(
                DocumentChunk.section_id.in_(selected_section_ids) & DocumentChunk.tsv.op("@@")(fts_query)
            ).limit(80)
            fts_rows_sec = list(db.execute(fts_stmt_sec).all())

        fts_stmt_global = base_bm25_pool.where(DocumentChunk.tsv.op("@@")(fts_query)).limit(120)
        fts_rows_global = list(db.execute(fts_stmt_global).all())

        fts_rows = fts_rows_sec + [r for r in fts_rows_global if r not in fts_rows_sec]
        if len(fts_rows) < 30:
            fts_rows = list(db.execute(base_bm25_pool.limit(800)).all())

        bm25_ranked: list[tuple[DocumentChunk, Document, Optional[DocumentSection], float]] = []
        if fts_rows:
            tokenized_docs = [_tokenize(row[0].text) for row in fts_rows]
            query_tokens = _tokenize(query)
            if query_tokens and any(tokenized_docs):
                bm25 = BM25Okapi(tokenized_docs)
                scores = bm25.get_scores(query_tokens)
                scored = [
                    (row[0], row[1], row[2], float(score))
                    for row, score in zip(fts_rows, scores, strict=True)
                    if float(score) > 0.0
                ]
                scored.sort(key=lambda item: item[3], reverse=True)
                bm25_ranked = scored[: self.settings.retrieval_top_k_bm25]
        bm25_ms = (time.perf_counter() - t_bm25_start) * 1000.0

        # 3. Reciprocal Rank Fusion (RRF, k=60)
        rrf_k = 60.0
        candidates: dict[uuid.UUID, RetrievedCandidate] = {}

        def _ensure_candidate(
            chunk: DocumentChunk, doc: Document, sec: Optional[DocumentSection]
        ) -> RetrievedCandidate:
            if chunk.id not in candidates:
                candidates[chunk.id] = RetrievedCandidate(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    doc_code=doc.doc_code,
                    document_title=doc.title,
                    source_url=doc.source_url,
                    licence=doc.licence,
                    mission=doc.mission,
                    section_id=sec.id if sec else chunk.section_id,
                    section_title=sec.title if sec else "Document Body",
                    section_path=sec.section_path if sec else "1",
                    page_number=chunk.page_number,
                    text=chunk.text,
                    bbox_json=list(chunk.bbox_json or []),
                )
            return candidates[chunk.id]

        for rank, (chunk, doc, sec, d_score) in enumerate(dense_rows, start=1):
            cand = _ensure_candidate(chunk, doc, sec)
            cand.dense_score = round(float(d_score), 4)
            cand.rrf_score += 1.0 / (rrf_k + rank)

        for rank, (chunk, doc, sec, b_score) in enumerate(bm25_ranked, start=1):
            cand = _ensure_candidate(chunk, doc, sec)
            cand.bm25_score = round(float(b_score), 4)
            cand.rrf_score += 1.0 / (rrf_k + rank)

        merged = sorted(candidates.values(), key=lambda c: c.rrf_score, reverse=True)[:20]
        for c in merged:
            c.rrf_score = round(c.rrf_score, 6)

        # 4. Cross-Encoder Reranking
        t_rerank_start = time.perf_counter()
        if merged:
            reranker = get_reranker()
            rerank_scores = reranker.score_pairs(query, [c.text for c in merged])
            for cand, r_score in zip(merged, rerank_scores, strict=True):
                cand.rerank_score = r_score
            merged.sort(key=lambda c: c.rerank_score, reverse=True)
        rerank_ms = (time.perf_counter() - t_rerank_start) * 1000.0

        top_results = merged[:final_k]
        total_ms = (time.perf_counter() - t0) * 1000.0

        telemetry = {
            "stair_level": selection_res.stair_level,
            "selector_name": selection_res.selector_name,
            "invalid_section_ids_count": selection_res.invalid_ids_count,
            "used_selector_fallback": selection_res.used_fallback,
            "selected_sections": [
                {
                    "section_id": str(m.section_id),
                    "document_id": str(m.document_id),
                    "doc_code": m.doc_code,
                    "section_path": m.section_path,
                    "title": m.title,
                    "page_start": m.page_start,
                    "page_end": m.page_end,
                    "reason": m.reason,
                }
                for m in selection_res.selected_sections
            ],
            "selected_section_ids": [str(s) for s in selected_section_ids]
            if selected_section_ids
            else None,
            "dense_count": len(dense_rows),
            "bm25_count": len(bm25_ranked),
            "rrf_pool_count": len(merged),
            "dense_ms": round(dense_ms, 2),
            "bm25_ms": round(bm25_ms, 2),
            "rerank_ms": round(rerank_ms, 2),
            "total_ms": round(total_ms, 2),
            "top_dense_score": max((c.dense_score for c in top_results), default=0.0),
            "top_bm25_score": max((c.bm25_score for c in top_results), default=0.0),
            "top_rrf_score": max((c.rrf_score for c in top_results), default=0.0),
            "top_rerank_score": max((c.rerank_score for c in top_results), default=0.0),
            "top_chunks": [
                {
                    "chunk_id": str(c.chunk_id),
                    "doc_code": c.doc_code,
                    "page": c.page_number,
                    "dense": c.dense_score,
                    "bm25": c.bm25_score,
                    "rrf": c.rrf_score,
                    "rerank": c.rerank_score,
                }
                for c in top_results
            ],
        }
        return top_results, telemetry
