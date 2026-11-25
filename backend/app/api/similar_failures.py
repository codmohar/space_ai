"""Similar Past Failures search endpoint (POST /api/similar-failures/search)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.failure_kg import MissionIncident
from app.schemas import (
    BBoxItem,
    RelevanceBreakdown,
    SimilarFailuresSearchRequest,
    SimilarFailuresSearchResponse,
    SimilarIncidentOut,
)
from app.services.incidents.indexer import IncidentKGIndexer
from app.services.incidents.similar_search import SimilarFailuresService

router = APIRouter(prefix="/api/similar-failures", tags=["similar-failures"])


def get_similar_service() -> SimilarFailuresService:
    return SimilarFailuresService()


def get_incident_indexer() -> IncidentKGIndexer:
    return IncidentKGIndexer()


@router.post("/search", response_model=SimilarFailuresSearchResponse)
def search_similar_failures(
    req: SimilarFailuresSearchRequest,
    db: Session = Depends(get_db),
) -> SimilarFailuresSearchResponse:
    if req.auto_index_if_empty:
        inc_count = db.execute(select(func.count(MissionIncident.id))).scalar_one()
        if int(inc_count) == 0:
            get_incident_indexer().index_all_documents(db=db, force_rebuild=False)

    profile, matches = get_similar_service().search(
        db=db,
        problem_description=req.problem_description,
        top_k=req.top_k,
        mission_filter=req.mission,
    )

    return SimilarFailuresSearchResponse(
        extracted_subsystems=profile.subsystems,
        extracted_mechanisms=profile.mechanisms,
        extracted_keywords=profile.keywords,
        risk_hypotheses=getattr(profile, "risk_hypotheses", []),
        design_risk_summary=getattr(profile, "design_risk_summary", ""),
        results=[
            SimilarIncidentOut(
                incident_id=m.incident.id,
                mission=m.incident.mission,
                subsystem=m.incident.subsystem,
                component=m.incident.component,
                anomaly_title=m.incident.anomaly_title,
                anomaly_description=m.incident.anomaly_description,
                root_cause=m.incident.root_cause,
                consequence=m.incident.consequence,
                corrective_action=m.incident.corrective_action,
                failure_mechanism=m.incident.failure_mechanism,
                evidence_classification=m.incident.evidence_classification,  # type: ignore[arg-type]
                verification_status=m.incident.verification_status,  # type: ignore[arg-type]
                document_id=m.doc.id,
                doc_code=m.doc.doc_code,
                document_title=m.doc.title,
                source_url=m.doc.source_url,
                licence=m.doc.licence,
                section=m.section_title,
                page_number=m.incident.page_number,
                chunk_id=m.incident.chunk_id,
                evidence_text=m.incident.evidence_text,
                bbox_json=[BBoxItem(**b) for b in m.bbox_json],
                relevance=RelevanceBreakdown(
                    semantic_score=m.semantic_score,
                    keyword_score=m.keyword_score,
                    rerank_score=m.rerank_score,
                    subsystem_match_score=m.subsystem_match_score,
                    matched_terms=m.matched_terms,
                    total_relevance=m.total_relevance,
                ),
            )
            for m in matches
        ],
    )
