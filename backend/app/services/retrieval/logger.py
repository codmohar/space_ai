"""Retrieval stage telemetry logging service."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.rag import RetrievalLog


def record_retrieval_log(
    db: Session,
    request_id: str,
    query_text: str,
    mission_scope: Optional[str],
    telemetry: dict[str, Any],
    confidence_category: str,
    abstained: bool,
    llm_model: Optional[str] = None,
) -> RetrievalLog:
    settings = get_settings()
    log = RetrievalLog(
        request_id=request_id,
        query_text=query_text,
        mission_scope=mission_scope,
        stair_level=telemetry.get("stair_level", "L1"),
        selected_section_ids=telemetry.get("selected_section_ids"),
        stage_scores=telemetry,
        top_rerank_score=telemetry.get("top_rerank_score"),
        confidence_category=confidence_category,
        abstained=abstained,
        latency_ms=telemetry.get("total_ms", 0.0),
        embedding_model=settings.embedding_model,
        reranker_model=settings.reranker_model,
        llm_model=llm_model,
        prompt_version=settings.prompt_version,
    )
    db.add(log)
    db.flush()
    return log
