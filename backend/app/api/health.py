"""Health and corpus telemetry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.eval import load_eval_results
from app.core.config import get_settings
from app.core.database import get_db
from app.models.documents import Document, DocumentChunk, DocumentSection
from app.models.rag import RetrievalLog
from app.schemas import CorpusStatsResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    db_ok = False
    pgvector_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
        ext = db.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
        pgvector_ok = ext == "vector"
    except Exception:  # noqa: BLE001
        db_ok = False

    return {
        "status": "ok" if db_ok and pgvector_ok else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "database": "connected" if db_ok else "error",
        "pgvector": "enabled" if pgvector_ok else "missing",
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "llm_provider": settings.llm_provider,
        "llm_configured": bool(settings.gemini_api_key),
    }


@router.get("/stats", response_model=CorpusStatsResponse)
def corpus_stats(db: Session = Depends(get_db)) -> CorpusStatsResponse:
    doc_count = db.execute(select(func.count(Document.id))).scalar_one()
    sec_count = db.execute(select(func.count(DocumentSection.id))).scalar_one()
    chk_count = db.execute(select(func.count(DocumentChunk.id))).scalar_one()
    ocr_count = db.execute(
        select(func.count(DocumentChunk.id)).where(DocumentChunk.ocr_used.is_(True))
    ).scalar_one()
    log_count = db.execute(select(func.count(RetrievalLog.id))).scalar_one()

    eval_res = load_eval_results()

    return CorpusStatsResponse(
        document_count=int(doc_count),
        section_count=int(sec_count),
        chunk_count=int(chk_count),
        ocr_chunk_count=int(ocr_count),
        retrieval_log_count=int(log_count),
        evaluation_status=eval_res.status,
    )
