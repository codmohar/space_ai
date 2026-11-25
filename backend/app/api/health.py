"""Health and corpus telemetry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.eval import load_eval_results
from app.core.config import get_settings
from app.core.database import get_db
from app.models.documents import Document, DocumentChunk, DocumentSection
from app.models.failure_kg import MissionEntity, MissionIncident
from app.models.rag import RetrievalLog
from app.schemas import CorpusStatsResponse

router = APIRouter(prefix="/api", tags=["health"])


def _check_models_warmed() -> dict[str, bool]:
    try:
        from app.services.retrieval.embeddings import get_embedding_model
        from app.services.retrieval.reranker import get_reranker_model

        embed_info = get_embedding_model.cache_info()
        rerank_info = get_reranker_model.cache_info()
        return {
            "embedding": embed_info.currsize > 0,
            "reranker": rerank_info.currsize > 0,
        }
    except Exception:  # noqa: BLE001
        return {"embedding": False, "reranker": False}


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    db_ok = False
    pgvector_ok = False
    incident_count = 0
    kg_entity_count = 0
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
        ext = db.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
        pgvector_ok = ext == "vector"
        incident_count = int(db.execute(select(func.count(MissionIncident.id))).scalar_one())
        kg_entity_count = int(db.execute(select(func.count(MissionEntity.id))).scalar_one())
    except Exception:  # noqa: BLE001
        db_ok = False

    eval_res = load_eval_results()
    models_warmed = _check_models_warmed()

    return {
        "status": "ok" if db_ok and pgvector_ok else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "database": "connected" if db_ok else "error",
        "pgvector": "enabled" if pgvector_ok else "missing",
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.gemini_model,
        "llm_configured": bool(settings.gemini_api_key),
        "prompt_version": settings.prompt_version,
        "auth_required": settings.auth_required,
        "models_warmed": models_warmed,
        "eval_status": eval_res.status,
        "incident_count": incident_count,
        "kg_entity_count": kg_entity_count,
    }


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)) -> dict:
    """Deep readiness probe verifying DB, pgvector, disk storage writeability, and model availability."""
    from pathlib import Path
    settings = get_settings()
    checks: dict[str, Any] = {}
    is_ready = True

    # 1. Database check
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"status": "error", "message": str(exc)}
        is_ready = False

    # 2. pgvector check
    try:
        ext = db.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).scalar_one_or_none()
        if ext == "vector":
            checks["pgvector"] = {"status": "ok"}
        else:
            checks["pgvector"] = {"status": "missing", "message": "pgvector extension is not enabled in database"}
            is_ready = False
    except Exception as exc:  # noqa: BLE001
        checks["pgvector"] = {"status": "error", "message": str(exc)}
        is_ready = False

    # 3. Storage directory writeability
    storage_path = Path(settings.storage_dir)
    try:
        storage_path.mkdir(parents=True, exist_ok=True)
        test_file = storage_path / ".ready_probe"
        test_file.write_text("ok")
        test_file.unlink(missing_ok=True)
        checks["storage"] = {"status": "ok", "path": str(storage_path)}
    except Exception as exc:  # noqa: BLE001
        checks["storage"] = {"status": "error", "path": str(storage_path), "message": str(exc)}
        is_ready = False

    # 4. Models
    checks["models_warmed"] = _check_models_warmed()

    return {
        "status": "ready" if is_ready else "not_ready",
        "service": settings.app_name,
        "version": settings.app_version,
        "checks": checks,
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
