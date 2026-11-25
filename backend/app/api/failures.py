"""Failure chain reconstruction and retrieval routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError
from app.models.documents import Document, DocumentChunk, DocumentSection
from app.models.failure_kg import FailureEvent, FailureRelationship
from app.schemas import (
    BBoxItem,
    FailureChainResponse,
    FailureEventOut,
    FailureReconstructRequest,
    FailureRelationshipOut,
)
from app.services.failures.reconstructor import FailureChainService

router = APIRouter(prefix="/api/failures", tags=["failures"])


def get_failure_service() -> FailureChainService:
    return FailureChainService()


def _serialize_events(db: Session, document_id: uuid.UUID) -> list[FailureEventOut]:
    rows = db.execute(
        select(FailureEvent, Document, DocumentChunk, DocumentSection)
        .join(Document, Document.id == FailureEvent.document_id)
        .join(DocumentChunk, DocumentChunk.id == FailureEvent.chunk_id)
        .outerjoin(DocumentSection, DocumentSection.id == FailureEvent.section_id)
        .where(FailureEvent.document_id == document_id)
        .order_by(FailureEvent.event_order.asc())
    ).all()

    return [
        FailureEventOut(
            id=ev.id,
            mission=ev.mission,
            event_type=ev.event_type,
            title=ev.title,
            description=ev.description,
            event_order=ev.event_order,
            timestamp_label=ev.timestamp_label,
            subsystem=ev.subsystem,
            evidence_classification=ev.evidence_classification,  # type: ignore[arg-type]
            verification_status=ev.verification_status,  # type: ignore[arg-type]
            document_id=doc.id,
            doc_code=doc.doc_code,
            document_title=doc.title,
            source_url=doc.source_url,
            licence=doc.licence,
            section_id=ev.section_id,
            section=sec.title if sec else "Document Body",
            page_number=ev.page_number,
            chunk_id=ev.chunk_id,
            evidence_text=ev.evidence_text,
            bbox_json=[BBoxItem(**b) for b in (chunk.bbox_json or [])],
        )
        for ev, doc, chunk, sec in rows
    ]


def _serialize_relationships(
    db: Session, document_id: uuid.UUID
) -> list[FailureRelationshipOut]:
    rels = (
        db.execute(
            select(FailureRelationship).where(
                FailureRelationship.document_id == document_id
            )
        )
        .scalars()
        .all()
    )
    return [
        FailureRelationshipOut(
            id=r.id,
            source_event_id=r.source_event_id,
            target_event_id=r.target_event_id,
            relationship_type=r.relationship_type,  # type: ignore[arg-type]
            verification_status=r.verification_status,  # type: ignore[arg-type]
            document_id=r.document_id,
            section_id=r.section_id,
            page_number=r.page_number,
            evidence_chunk_id=r.evidence_chunk_id,
            evidence_text=r.evidence_text,
        )
        for r in rels
    ]


@router.post("/reconstruct", response_model=FailureChainResponse)
def reconstruct_failure_chain(
    req: FailureReconstructRequest,
    db: Session = Depends(get_db),
) -> FailureChainResponse:
    service = get_failure_service()
    res = service.reconstruct_for_document(
        db=db,
        document_id=req.document_id,
        force_rebuild=req.force_rebuild,
    )
    events_out = _serialize_events(db, res.document.id)
    rels_out = _serialize_relationships(db, res.document.id)
    return FailureChainResponse(
        document_id=res.document.id,
        doc_code=res.document.doc_code,
        document_title=res.document.title,
        mission=res.document.mission,
        events=events_out,
        relationships=rels_out,
        verified_events=res.verified_events,
        verified_relationships=res.verified_relationships,
    )


@router.get("/{document_id}/events", response_model=list[FailureEventOut])
def get_failure_events(
    document_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[FailureEventOut]:
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", status_code=404)
    return _serialize_events(db, document_id)


@router.get("/{document_id}/relationships", response_model=list[FailureRelationshipOut])
def get_failure_relationships(
    document_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[FailureRelationshipOut]:
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", status_code=404)
    return _serialize_relationships(db, document_id)
