"""Document upload, ingestion, listing, ToC, page chunks, and PDF file serving routes."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError
from app.models.documents import Document, DocumentChunk, DocumentSection
from app.schemas import (
    BBoxItem,
    DocumentPageResponse,
    DocumentSectionNode,
    DocumentSummary,
    IngestRequest,
    IngestResponse,
    PageChunkView,
)
from app.services.ingestion.pipeline import IngestionPipeline

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=IngestResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_code: str = Form(...),
    title: str = Form(...),
    source_url: str = Form(...),
    licence: str = Form(...),
    org: str = Form("NASA"),
    mission: str = Form("Unknown"),
    version: str = Form("1.0"),
    db: Session = Depends(get_db),
) -> IngestResponse:
    raw_bytes = await file.read()
    pipeline = IngestionPipeline()
    res = pipeline.ingest_bytes(
        db=db,
        raw_bytes=raw_bytes,
        filename=file.filename or "report.pdf",
        doc_code=doc_code,
        title=title,
        source_url=source_url,
        licence=licence,
        org=org,
        mission=mission,
        version=version,
        content_type=file.content_type,
    )
    return IngestResponse(
        document_id=res.document_id,
        doc_code=res.doc_code,
        status=res.status,
        page_count=res.page_count,
        section_count=res.section_count,
        chunk_count=res.chunk_count,
        ocr_pages=res.ocr_pages,
    )


@router.post("/ingest", response_model=IngestResponse)
def ingest_local_document(
    req: IngestRequest,
    db: Session = Depends(get_db),
) -> IngestResponse:
    pdf_path = Path(req.file_path)
    if not pdf_path.exists() or not pdf_path.is_file():
        raise ApiError(
            "FILE_NOT_FOUND",
            f"Document file not found: {req.file_path}",
            status_code=404,
        )
    pipeline = IngestionPipeline()
    res = pipeline.ingest_file(
        db=db,
        file_path=pdf_path,
        doc_code=req.doc_code,
        title=req.title,
        source_url=req.source_url,
        licence=req.licence,
        org=req.org,
        mission=req.mission,
        version=req.version,
    )
    return IngestResponse(
        document_id=res.document_id,
        doc_code=res.doc_code,
        status=res.status,
        page_count=res.page_count,
        section_count=res.section_count,
        chunk_count=res.chunk_count,
        ocr_pages=res.ocr_pages,
    )


@router.get("", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentSummary]:
    docs = db.execute(select(Document).order_by(Document.created_at.desc())).scalars().all()
    summaries: list[DocumentSummary] = []
    for d in docs:
        chunk_count = db.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == d.id)
        ).scalar_one()
        section_count = db.execute(
            select(func.count(DocumentSection.id)).where(DocumentSection.document_id == d.id)
        ).scalar_one()
        summaries.append(
            DocumentSummary(
                id=d.id,
                doc_code=d.doc_code,
                title=d.title,
                source_url=d.source_url,
                licence=d.licence,
                org=d.org,
                mission=d.mission,
                page_count=d.page_count,
                version=d.version,
                ingestion_status=d.ingestion_status,
                chunk_count=int(chunk_count),
                section_count=int(section_count),
                created_at=d.created_at,
            )
        )
    return summaries


@router.get("/{document_id}/toc", response_model=list[DocumentSectionNode])
def get_document_toc(
    document_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[DocumentSectionNode]:
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", status_code=404)

    sections = (
        db.execute(
            select(DocumentSection)
            .where(DocumentSection.document_id == document_id)
            .order_by(DocumentSection.order_index.asc())
        )
        .scalars()
        .all()
    )
    return [
        DocumentSectionNode(
            id=s.id,
            parent_id=s.parent_id,
            title=s.title,
            level=s.level,
            is_leaf=s.is_leaf,
            section_path=s.section_path,
            page_start=s.page_start,
            page_end=s.page_end,
            order_index=s.order_index,
            extraction_method=s.extraction_method,
        )
        for s in sections
    ]


@router.get("/{document_id}/pages/{page}", response_model=DocumentPageResponse)
def get_document_page(
    document_id: uuid.UUID, page: int, db: Session = Depends(get_db)
) -> DocumentPageResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", status_code=404)
    if page < 1 or page > max(1, doc.page_count):
        raise ApiError(
            "INVALID_PAGE_NUMBER",
            f"Page {page} out of range (1..{doc.page_count}).",
            status_code=400,
        )

    rows = db.execute(
        select(DocumentChunk, DocumentSection)
        .outerjoin(DocumentSection, DocumentSection.id == DocumentChunk.section_id)
        .where(DocumentChunk.document_id == document_id, DocumentChunk.page_number == page)
        .order_by(DocumentChunk.chunk_index.asc())
    ).all()

    chunks = [
        PageChunkView(
            id=c.id,
            chunk_index=c.chunk_index,
            page_number=c.page_number,
            section_id=c.section_id,
            section_title=s.title if s else None,
            section_path=s.section_path if s else None,
            text=c.text,
            bbox_json=[BBoxItem(**b) for b in (c.bbox_json or [])],
            ocr_used=c.ocr_used,
            ocr_confidence=c.ocr_confidence,
        )
        for c, s in rows
    ]

    return DocumentPageResponse(
        document_id=doc.id,
        doc_code=doc.doc_code,
        title=doc.title,
        source_url=doc.source_url,
        licence=doc.licence,
        page_number=page,
        page_count=doc.page_count,
        chunks=chunks,
    )


@router.get("/{document_id}/file")
def get_document_pdf_file(document_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", status_code=404)
    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise ApiError(
            "PDF_FILE_MISSING",
            f"Stored PDF file missing on disk for {doc.doc_code}.",
            status_code=404,
        )
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=f"{doc.doc_code}.pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.doc_code}.pdf"'},
    )
