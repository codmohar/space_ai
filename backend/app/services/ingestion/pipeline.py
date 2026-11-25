"""Shared PDF ingestion pipeline: validation, hash dedupe, extraction, chunking, embedding."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    safe_filename,
    validate_pdf_bytes,
    validate_provenance_fields,
    validate_upload_bytes,
)
from app.models.documents import (
    Document,
    DocumentChunk,
    DocumentEmbedding,
    DocumentSection,
    DocumentVersion,
)
from app.services.ingestion.chunker import chunk_extracted_document
from app.services.ingestion.format_parsers import UniversalDocumentParser
from app.services.ingestion.pdf_extractor import extract_pdf
from app.services.retrieval.embeddings import get_embedding_service


@dataclass
class IngestionResult:
    document_id: uuid.UUID
    doc_code: str
    status: str  # ingested | duplicate
    page_count: int
    section_count: int
    chunk_count: int
    ocr_pages: int


class IngestionPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()

    def ingest_bytes(
        self,
        db: Session,
        raw_bytes: bytes,
        filename: str,
        doc_code: str,
        title: str,
        source_url: str,
        licence: str,
        org: str = "NASA",
        mission: str = "Unknown",
        version: str = "1.0",
        classification: str = "public",
        content_type: str | None = None,
    ) -> IngestionResult:
        clean_url, clean_licence = validate_provenance_fields(source_url, licence)
        file_hash = validate_upload_bytes(
            raw_bytes,
            filename=filename,
            content_type=content_type,
            max_upload_mb=self.settings.max_upload_mb,
            max_upload_pages=self.settings.max_upload_pages,
        )

        # Hash-based deduplication
        existing = db.execute(
            select(Document).where(Document.file_hash == file_hash)
        ).scalar_one_or_none()
        if existing is not None:
            sec_count = len(existing.sections)
            chk_count = len(existing.chunks)
            return IngestionResult(
                document_id=existing.id,
                doc_code=existing.doc_code,
                status="duplicate",
                page_count=existing.page_count,
                section_count=sec_count,
                chunk_count=chk_count,
                ocr_pages=0,
            )

        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{file_hash[:12]}_{safe_filename(filename)}"
        stored_path = self.settings.storage_dir / stored_name
        stored_path.write_bytes(raw_bytes)

        return self._persist_extracted_document(
            db=db,
            raw_bytes=raw_bytes,
            file_path=stored_path,
            file_hash=file_hash,
            doc_code=doc_code.strip(),
            title=title.strip(),
            source_url=clean_url,
            licence=clean_licence,
            org=org.strip() or "NASA",
            mission=mission.strip() or "Unknown",
            version=version.strip() or "1.0",
            classification=classification.strip() or "public",
        )

    def ingest_file(
        self,
        db: Session,
        file_path: Path,
        doc_code: str,
        title: str,
        source_url: str,
        licence: str,
        org: str = "NASA",
        mission: str = "Unknown",
        version: str = "1.0",
        classification: str = "public",
    ) -> IngestionResult:
        raw_bytes = file_path.read_bytes()
        clean_url, clean_licence = validate_provenance_fields(source_url, licence)
        file_hash = validate_upload_bytes(
            raw_bytes,
            filename=file_path.name,
            content_type=None,
            max_upload_mb=self.settings.max_upload_mb,
        )

        existing = db.execute(
            select(Document).where(Document.file_hash == file_hash)
        ).scalar_one_or_none()
        if existing is not None:
            return IngestionResult(
                document_id=existing.id,
                doc_code=existing.doc_code,
                status="duplicate",
                page_count=existing.page_count,
                section_count=len(existing.sections),
                chunk_count=len(existing.chunks),
                ocr_pages=0,
            )

        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{file_hash[:12]}_{safe_filename(file_path.name)}"
        stored_path = self.settings.storage_dir / stored_name
        if not stored_path.exists():
            shutil.copy2(file_path, stored_path)

        return self._persist_extracted_document(
            db=db,
            raw_bytes=raw_bytes,
            file_path=stored_path,
            file_hash=file_hash,
            doc_code=doc_code.strip(),
            title=title.strip(),
            source_url=clean_url,
            licence=clean_licence,
            org=org.strip() or "NASA",
            mission=mission.strip() or "Unknown",
            version=version.strip() or "1.0",
            classification=classification.strip() or "public",
        )

    def _persist_extracted_pdf(
        self,
        db: Session,
        pdf_path: Path,
        file_hash: str,
        doc_code: str,
        title: str,
        source_url: str,
        licence: str,
        org: str,
        mission: str,
        version: str,
        classification: str = "public",
    ) -> IngestionResult:
        raw_bytes = pdf_path.read_bytes()
        return self._persist_extracted_document(
            db=db,
            raw_bytes=raw_bytes,
            file_path=pdf_path,
            file_hash=file_hash,
            doc_code=doc_code,
            title=title,
            source_url=source_url,
            licence=licence,
            org=org,
            mission=mission,
            version=version,
            classification=classification,
        )

    def _persist_extracted_document(
        self,
        db: Session,
        raw_bytes: bytes,
        file_path: Path,
        file_hash: str,
        doc_code: str,
        title: str,
        source_url: str,
        licence: str,
        org: str,
        mission: str,
        version: str,
        classification: str = "public",
    ) -> IngestionResult:
        extracted = UniversalDocumentParser.extract(raw_bytes=raw_bytes, filename=file_path.name)
        chunk_drafts = chunk_extracted_document(extracted)

        doc = Document(
            doc_code=doc_code,
            title=title,
            source_url=source_url,
            licence=licence,
            org=org,
            mission=mission,
            file_path=str(file_path.resolve()),
            file_hash=file_hash,
            page_count=extracted.page_count,
            version=version,
            classification=classification,
            ingestion_status="completed",
            metadata_json={
                "pdf_metadata": extracted.pdf_metadata,
                "ocr_pages": extracted.ocr_pages,
                "low_quality_ocr_pages": extracted.low_quality_ocr_pages,
                "toc_extraction_method": extracted.toc_extraction_method,
            },
        )
        db.add(doc)
        db.flush()

        db.add(
            DocumentVersion(
                document_id=doc.id,
                version=version,
                file_hash=file_hash,
                file_path=str(pdf_path.resolve()),
                notes="Initial ingestion",
            )
        )

        # Insert sections preserving parent links
        temp_to_uuid: dict[int, uuid.UUID] = {}
        for sec in extracted.sections:
            sec_id = uuid.uuid4()
            temp_to_uuid[sec.temp_id] = sec_id
            parent_uuid = (
                temp_to_uuid.get(sec.parent_temp_id) if sec.parent_temp_id is not None else None
            )
            db.add(
                DocumentSection(
                    id=sec_id,
                    document_id=doc.id,
                    parent_id=parent_uuid,
                    title=sec.title,
                    level=sec.level,
                    is_leaf=sec.is_leaf,
                    section_path=sec.section_path,
                    page_start=sec.page_start,
                    page_end=sec.page_end,
                    order_index=sec.order_index,
                    extraction_method=sec.extraction_method,
                )
            )
        db.flush()

        chunk_models: list[DocumentChunk] = []
        for draft in chunk_drafts:
            cm = DocumentChunk(
                document_id=doc.id,
                section_id=temp_to_uuid.get(draft.section_temp_id),
                chunk_index=draft.chunk_index,
                page_number=draft.page_number,
                bbox_json=draft.bbox_json,
                text=draft.text,
                token_count=draft.token_count,
                ocr_used=draft.ocr_used,
                ocr_confidence=draft.ocr_confidence,
                metadata_json=draft.metadata_json,
            )
            db.add(cm)
            chunk_models.append(cm)
        db.flush()

        # Generate and store pgvector embeddings
        embedder = get_embedding_service()
        vectors = embedder.embed_passages([c.text for c in chunk_models])
        for cm, vec in zip(chunk_models, vectors, strict=True):
            db.add(
                DocumentEmbedding(
                    chunk_id=cm.id,
                    model_name=embedder.model_name,
                    embedding=vec,
                )
            )

        db.commit()
        return IngestionResult(
            document_id=doc.id,
            doc_code=doc.doc_code,
            status="ingested",
            page_count=extracted.page_count,
            section_count=len(extracted.sections),
            chunk_count=len(chunk_models),
            ocr_pages=extracted.ocr_pages,
        )
