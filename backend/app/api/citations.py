"""Citation resolution endpoint returning chunk provenance and bounding boxes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError
from app.models.documents import Document, DocumentChunk, DocumentSection
from app.models.rag import Citation
from app.schemas import BBoxItem, CitationOut

router = APIRouter(prefix="/api/citations", tags=["citations"])


@router.get("/{citation_id}", response_model=CitationOut)
def get_citation(citation_id: uuid.UUID, db: Session = Depends(get_db)) -> CitationOut:
    row = db.execute(
        select(Citation, Document, DocumentChunk, DocumentSection)
        .join(Document, Document.id == Citation.document_id)
        .join(DocumentChunk, DocumentChunk.id == Citation.chunk_id)
        .outerjoin(DocumentSection, DocumentSection.id == Citation.section_id)
        .where(Citation.id == citation_id)
    ).first()

    if row is None:
        raise ApiError("CITATION_NOT_FOUND", "Citation not found.", status_code=404)

    cit, doc, chunk, sec = row
    return CitationOut(
        id=cit.id,
        document_id=doc.id,
        doc_code=doc.doc_code,
        document_title=doc.title,
        source_url=doc.source_url,
        licence=doc.licence,
        section_id=cit.section_id,
        section=sec.title if sec else "Document Body",
        page_number=cit.page_number,
        chunk_id=chunk.id,
        quote=cit.evidence_text,
        bbox_json=[BBoxItem(**b) for b in (chunk.bbox_json or [])],
        verified=cit.verified,
    )
