"""Hybrid retrieval search route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import (
    BBoxItem,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    RetrievedChunkOut,
)
from app.services.retrieval.hybrid import HybridRetriever

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])


@router.post("/search", response_model=RetrievalSearchResponse)
def hybrid_search(
    req: RetrievalSearchRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> RetrievalSearchResponse:
    retriever = HybridRetriever()
    candidates, telemetry = retriever.search(
        db=db,
        query=req.query,
        mission=req.mission,
        document_ids=req.document_ids,
        top_k=req.top_k,
    )
    request_id = getattr(request.state, "request_id", "unknown")

    return RetrievalSearchResponse(
        request_id=request_id,
        stair_level=telemetry.get("stair_level", "L1"),
        latency_ms=telemetry.get("total_ms", 0.0),
        results=[
            RetrievedChunkOut(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                doc_code=c.doc_code,
                document_title=c.document_title,
                source_url=c.source_url,
                licence=c.licence,
                mission=c.mission,
                section_id=c.section_id,
                section_title=c.section_title,
                section_path=c.section_path,
                page_number=c.page_number,
                text=c.text,
                bbox_json=[BBoxItem(**b) for b in c.bbox_json],
                dense_score=c.dense_score,
                bm25_score=c.bm25_score,
                rrf_score=c.rrf_score,
                rerank_score=c.rerank_score,
            )
            for c in candidates
        ],
    )
