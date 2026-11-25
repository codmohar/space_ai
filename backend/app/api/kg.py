"""Engineering Knowledge Graph indexing, graph retrieval, and multi-hop query routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.auth import User
from app.schemas import (
    KGGraphResponse,
    KGIndexReportSummary,
    KGIndexRequest,
    KGQueryRequest,
    KGQueryResponse,
)
from app.services.audit import record_audit_log
from app.services.auth.security import get_optional_user
from app.services.incidents.indexer import IncidentKGIndexer
from app.services.kg.service import KnowledgeGraphService

router = APIRouter(prefix="/api/kg", tags=["knowledge-graph"])


def get_indexer() -> IncidentKGIndexer:
    return IncidentKGIndexer()


def get_kg_service() -> KnowledgeGraphService:
    return KnowledgeGraphService()


@router.post("/index", response_model=list[KGIndexReportSummary])
def index_incidents_and_kg(
    req: KGIndexRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> list[KGIndexReportSummary]:
    indexer = get_indexer()
    if req.document_id is not None:
        results = [
            indexer.index_document(
                db=db, document_id=req.document_id, force_rebuild=req.force_rebuild
            )
        ]
    else:
        results = indexer.index_all_documents(db=db, force_rebuild=req.force_rebuild)

    record_audit_log(
        db=db,
        action="kg.index",
        resource_type="knowledge_graph",
        resource_id=str(req.document_id) if req.document_id else "all",
        user_id=current_user.id if current_user else None,
        request_id=getattr(request.state, "request_id", None),
        details={"documents_indexed": len(results)},
    )
    db.commit()

    return [
        KGIndexReportSummary(
            document_id=r.document_id,
            doc_code=r.doc_code,
            incidents_indexed=r.incidents_indexed,
            verified_incidents=r.verified_incidents,
            entities_created=r.entities_created,
            relations_created=r.relations_created,
        )
        for r in results
    ]


@router.get("/graph", response_model=KGGraphResponse)
def get_knowledge_graph(
    mission: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> KGGraphResponse:
    nodes, edges = get_kg_service().get_graph(
        db=db,
        mission=mission,
        entity_type=entity_type,
        limit=min(400, max(10, limit)),
    )
    return KGGraphResponse.model_validate({"nodes": nodes, "edges": edges})


@router.post("/query", response_model=KGQueryResponse)
def query_knowledge_graph(
    req: KGQueryRequest,
    db: Session = Depends(get_db),
) -> KGQueryResponse:
    res = get_kg_service().query_multihop(
        db=db,
        query=req.query,
        mission_filter=req.mission,
    )
    return KGQueryResponse.model_validate(res)
