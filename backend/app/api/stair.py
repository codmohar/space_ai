"""STAIR ToC-to-leaf retrieval endpoint (POST /api/stair/retrieve)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.documents import Document
from app.schemas import (
    BBoxItem,
    RetrievedChunkOut,
    STAIRRetrieveRequest,
    STAIRRetrieveResponse,
    SelectedSectionOut,
)
from app.services.retrieval.hybrid import HybridRetriever
from app.services.retrieval.section_selector import build_section_selector

router = APIRouter(prefix="/api/stair", tags=["stair"])


@router.post("/retrieve", response_model=STAIRRetrieveResponse)
def stair_retrieve(
    req: STAIRRetrieveRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> STAIRRetrieveResponse:
    scoped_doc_ids = req.document_ids
    if req.mission and not scoped_doc_ids:
        mission_docs = (
            db.execute(
                select(Document.id).where(func.lower(Document.mission) == req.mission.strip().lower())
            )
            .scalars()
            .all()
        )
        if mission_docs:
            scoped_doc_ids = list(mission_docs)

    selector = build_section_selector(mode=req.selector_mode)
    sel_res = selector.select(
        db=db,
        query=req.query,
        document_ids=scoped_doc_ids,
        top_k_sections=req.top_k_sections,
    )

    # Reuse the shared hybrid retrieval pipeline scoped to selected leaf sections
    retriever = HybridRetriever(section_selector=selector)
    candidates, telemetry = retriever.search(
        db=db,
        query=req.query,
        mission=req.mission,
        document_ids=scoped_doc_ids,
        top_k=req.top_k_chunks,
    )
    request_id = getattr(request.state, "request_id", "unknown")

    return STAIRRetrieveResponse(
        request_id=request_id,
        stair_level=sel_res.stair_level,
        selector_name=sel_res.selector_name,
        invalid_ids_count=sel_res.invalid_ids_count,
        used_fallback=sel_res.used_fallback,
        stub_not_trained=sel_res.stub_not_trained,
        selected_sections=[
            SelectedSectionOut(
                section_id=m.section_id,
                document_id=m.document_id,
                doc_code=m.doc_code,
                section_path=m.section_path,
                title=m.title,
                page_start=m.page_start,
                page_end=m.page_end,
                reason=m.reason,
            )
            for m in sel_res.selected_sections
        ],
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
        latency_ms=telemetry.get("total_ms", 0.0),
    )
