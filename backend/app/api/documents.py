"""Document upload, ingestion, listing, ToC, page chunks, and PDF file serving routes."""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError
from app.models.auth import User
from app.models.documents import Document, DocumentChunk, DocumentSection, IngestionJob
from app.schemas import (
    BBoxItem,
    DocumentPageResponse,
    DocumentSectionNode,
    DocumentSummary,
    IngestRequest,
    IngestResponse,
    IngestionJobOut,
    JobCancelResponse,
    PageChunkView,
    SupportedFormatInfo,
)
from app.services.audit import record_audit_log
from app.services.auth.security import get_optional_user
from app.services.ingestion.format_parsers import UniversalDocumentParser
from app.services.ingestion.job_queue import IngestionJobManager
from app.services.ingestion.pipeline import IngestionPipeline

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/supported-formats", response_model=list[SupportedFormatInfo])
def get_supported_formats() -> list[SupportedFormatInfo]:
    """Returns all document formats verified to pass parsing and ingestion tests."""
    ext_mimes = {
        ".pdf": ("PDF Report", "application/pdf", True),
        ".docx": ("Microsoft Word", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", False),
        ".pptx": ("PowerPoint Slides", "application/vnd.openxmlformats-officedocument.presentationml.presentation", False),
        ".txt": ("Plain Text Document", "text/plain", False),
        ".md": ("Markdown Document", "text/markdown", False),
        ".html": ("HTML Web Document", "text/html", False),
        ".csv": ("CSV Data Sheet", "text/csv", False),
        ".xlsx": ("Excel Spreadsheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", False),
        ".xml": ("XML Telemetry/Data", "application/xml", False),
        ".png": ("PNG Image Scan", "image/png", True),
        ".jpg": ("JPEG Image Scan", "image/jpeg", True),
        ".tiff": ("TIFF Image Scan", "image/tiff", True),
    }
    return [
        SupportedFormatInfo(extension=ext, label=label, mime=mime, ocr_enabled=ocr)
        for ext, (label, mime, ocr) in ext_mimes.items()
    ]


def _resolve_upload_metadata(
    filename: str,
    raw_bytes: bytes,
    doc_code: Optional[str] = None,
    title: Optional[str] = None,
    source_url: Optional[str] = None,
    licence: Optional[str] = None,
    org: Optional[str] = None,
    organization: Optional[str] = None,
    mission: Optional[str] = None,
) -> tuple[str, str, str, str, str, str]:
    """Auto-derives missing metadata gracefully so UI and API uploads never fail validation."""
    clean_stem = Path(filename).stem
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "-", clean_stem).strip("-") or "DOC"
    
    # 1. Organization
    resolved_org = (org or organization or "NASA").strip()
    
    # 2. Mission
    resolved_mission = (mission or "Aerospace Engineering").strip()
    
    # 3. Document Code
    if doc_code and doc_code.strip():
        resolved_doc_code = doc_code.strip().upper()
    else:
        sha_prefix = hashlib.sha256(raw_bytes[:4096]).hexdigest()[:6].upper()
        resolved_doc_code = f"{resolved_org[:4].upper()}-{safe_name[:12].upper()}-{sha_prefix}"

    # 4. Title
    if title and title.strip():
        resolved_title = title.strip()
    else:
        resolved_title = clean_stem.replace("_", " ").replace("-", " ").title()

    # 5. Source URL
    resolved_source_url = (source_url or "uploaded, no public URL").strip()

    # 6. Licence
    resolved_licence = (licence or "Public Domain / NASA Technical Report").strip()

    return (
        resolved_doc_code,
        resolved_title,
        resolved_source_url,
        resolved_licence,
        resolved_org,
        resolved_mission,
    )


@router.post("/upload", response_model=IngestResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    doc_code: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    licence: Optional[str] = Form(None),
    org: Optional[str] = Form(None),
    organization: Optional[str] = Form(None),
    mission: Optional[str] = Form(None),
    version: str = Form("1.0"),
    classification: str = Form("public"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> IngestResponse:
    raw_bytes = await file.read()
    filename = file.filename or "report.pdf"
    (
        c_doc_code,
        c_title,
        c_source_url,
        c_licence,
        c_org,
        c_mission,
    ) = _resolve_upload_metadata(
        filename=filename,
        raw_bytes=raw_bytes,
        doc_code=doc_code,
        title=title,
        source_url=source_url,
        licence=licence,
        org=org,
        organization=organization,
        mission=mission,
    )

    pipeline = IngestionPipeline()
    res = pipeline.ingest_bytes(
        db=db,
        raw_bytes=raw_bytes,
        filename=filename,
        doc_code=c_doc_code,
        title=c_title,
        source_url=c_source_url,
        licence=c_licence,
        org=c_org,
        mission=c_mission,
        version=version,
        classification=classification,
        content_type=file.content_type,
    )
    record_audit_log(
        db=db,
        action="document.upload",
        resource_type="document",
        resource_id=str(res.document_id),
        user_id=current_user.id if current_user else None,
        request_id=getattr(request.state, "request_id", None),
        details={
            "doc_code": res.doc_code,
            "status": res.status,
            "page_count": res.page_count,
            "chunk_count": res.chunk_count,
            "ocr_pages": res.ocr_pages,
            "classification": classification,
        },
    )
    db.commit()
    return IngestResponse(
        document_id=res.document_id,
        doc_code=res.doc_code,
        status=res.status,
        page_count=res.page_count,
        section_count=res.section_count,
        chunk_count=res.chunk_count,
        ocr_pages=res.ocr_pages,
    )


@router.post("/upload/async", response_model=IngestionJobOut)
async def upload_document_async(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    doc_code: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    licence: Optional[str] = Form(None),
    org: Optional[str] = Form(None),
    organization: Optional[str] = Form(None),
    mission: Optional[str] = Form(None),
    version: str = Form("1.0"),
    classification: str = Form("public"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> IngestionJobOut:
    raw_bytes = await file.read()
    filename = file.filename or "report.pdf"
    (
        c_doc_code,
        c_title,
        c_source_url,
        c_licence,
        c_org,
        c_mission,
    ) = _resolve_upload_metadata(
        filename=filename,
        raw_bytes=raw_bytes,
        doc_code=doc_code,
        title=title,
        source_url=source_url,
        licence=licence,
        org=org,
        organization=organization,
        mission=mission,
    )

    manager = IngestionJobManager()
    job = manager.create_job(
        db=db,
        filename=filename,
        doc_code=c_doc_code,
        title=c_title,
        source_url=c_source_url,
        licence=c_licence,
        raw_bytes=raw_bytes,
        org=c_org,
        mission=c_mission,
        version=version,
        classification=classification,
        content_type=file.content_type,
    )

    # Dispatch to background task execution
    background_tasks.add_task(
        manager.execute_job_sync,
        job_id=job.job_id,
        raw_bytes=raw_bytes,
        filename=filename,
        doc_code=c_doc_code,
        title=c_title,
        source_url=c_source_url,
        licence=c_licence,
        org=c_org,
        mission=c_mission,
        version=version,
        classification=classification,
        content_type=file.content_type,
    )

    record_audit_log(
        db=db,
        action="document.upload_async",
        resource_type="ingestion_job",
        resource_id=job.job_id,
        user_id=current_user.id if current_user else None,
        request_id=getattr(request.state, "request_id", None),
        details={"doc_code": doc_code, "filename": filename, "status": "queued"},
    )
    db.commit()

    return IngestionJobOut(
        job_id=job.job_id,
        doc_code=job.doc_code,
        filename=job.filename,
        file_type=job.file_type,
        status=job.status,
        progress_pct=job.progress_pct,
        document_id=job.document_id,
        error_message=job.error_message,
        logs=job.logs or [],
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs", response_model=list[IngestionJobOut])
def list_ingestion_jobs(
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[IngestionJobOut]:
    manager = IngestionJobManager()
    jobs = manager.list_jobs(db=db, limit=limit)
    return [
        IngestionJobOut(
            job_id=j.job_id,
            doc_code=j.doc_code,
            filename=j.filename,
            file_type=j.file_type,
            status=j.status,
            progress_pct=j.progress_pct,
            document_id=j.document_id,
            error_message=j.error_message,
            logs=j.logs or [],
            created_at=j.created_at,
            updated_at=j.updated_at,
        )
        for j in jobs
    ]


@router.get("/jobs/{job_id}", response_model=IngestionJobOut)
def get_ingestion_job_status(job_id: str, db: Session = Depends(get_db)) -> IngestionJobOut:
    manager = IngestionJobManager()
    job = manager.get_job(db=db, job_id=job_id)
    if not job:
        raise ApiError("JOB_NOT_FOUND", f"Job '{job_id}' not found", status_code=404)
    return IngestionJobOut(
        job_id=job.job_id,
        doc_code=job.doc_code,
        filename=job.filename,
        file_type=job.file_type,
        status=job.status,
        progress_pct=job.progress_pct,
        document_id=job.document_id,
        error_message=job.error_message,
        logs=job.logs or [],
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/jobs/{job_id}/cancel", response_model=JobCancelResponse)
def cancel_ingestion_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> JobCancelResponse:
    manager = IngestionJobManager()
    success = manager.cancel_job(db=db, job_id=job_id)
    if not success:
        raise ApiError("CANNOT_CANCEL_JOB", f"Job '{job_id}' cannot be cancelled (may be completed or missing).", status_code=400)
    return JobCancelResponse(job_id=job_id, status="cancelled", message="Job cancellation requested.")


@router.post("/{document_id}/reindex", response_model=IngestResponse)
def reindex_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> IngestResponse:
    manager = IngestionJobManager()
    res = manager.reindex_document(db=db, document_id=document_id)
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
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
    record_audit_log(
        db=db,
        action="document.ingest",
        resource_type="document",
        resource_id=str(res.document_id),
        user_id=current_user.id if current_user else None,
        request_id=getattr(request.state, "request_id", None),
        details={
            "doc_code": res.doc_code,
            "status": res.status,
            "page_count": res.page_count,
            "chunk_count": res.chunk_count,
        },
    )
    db.commit()
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
def list_documents(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> list[DocumentSummary]:
    allowed = ["public"]
    if current_user:
        r_name = getattr(current_user.role, "name", "")
        if r_name == "admin":
            allowed = ["public", "internal", "restricted"]
        elif r_name == "engineer":
            allowed = ["public", "internal"]

    docs = (
        db.execute(
            select(Document)
            .where(Document.classification.in_(allowed))
            .order_by(Document.created_at.desc())
        )
        .scalars()
        .all()
    )
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
                classification=d.classification,
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
def get_document_pdf_file(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> FileResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", status_code=404)

    # Classification authorization check before serving file
    if doc.classification in ("internal", "restricted"):
        if not current_user:
            raise ApiError(
                "UNAUTHORIZED",
                f"Authentication required to access {doc.classification} document.",
                status_code=401,
            )
        role_name = getattr(current_user.role, "name", "")
        if doc.classification == "restricted" and role_name != "admin":
            raise ApiError(
                "FORBIDDEN",
                "Admin clearance required to access restricted document.",
                status_code=403,
            )
        if doc.classification == "internal" and role_name not in ("admin", "engineer"):
            raise ApiError(
                "FORBIDDEN",
                "Engineer clearance required to access internal document.",
                status_code=403,
            )

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise ApiError(
            "FILE_MISSING",
            f"Stored document file missing on disk for {doc.doc_code}.",
            status_code=404,
        )

    ext = file_path.suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".html": "text/html",
        ".htm": "text/html",
        ".csv": "text/csv",
        ".xml": "application/xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
        headers={"Content-Disposition": f'inline; filename="{file_path.name}"'},
    )
