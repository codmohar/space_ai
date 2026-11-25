"""Pydantic v2 API schemas for documents, retrieval, RAG chat, and citations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

EvidenceClassification = Literal[
    "explicitly_stated",
    "official_root_cause",
    "official_contributing_factor",
    "system_inference",
    "unknown",
]

ConfidenceCategory = Literal["Strong", "Partial", "Conflicting", "Insufficient", "None"]


class BBoxItem(BaseModel):
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float
    page_height: float


class DocumentSummary(BaseModel):
    id: uuid.UUID
    doc_code: str
    title: str
    source_url: str
    licence: str
    org: str
    mission: str
    page_count: int
    version: str
    ingestion_status: str
    chunk_count: int = 0
    section_count: int = 0
    created_at: datetime


class DocumentSectionNode(BaseModel):
    id: uuid.UUID
    parent_id: Optional[uuid.UUID]
    title: str
    level: int
    is_leaf: bool
    section_path: str
    page_start: int
    page_end: int
    order_index: int


class PageChunkView(BaseModel):
    id: uuid.UUID
    chunk_index: int
    page_number: int
    section_id: Optional[uuid.UUID]
    section_title: Optional[str] = None
    section_path: Optional[str] = None
    text: str
    bbox_json: list[BBoxItem]
    ocr_used: bool
    ocr_confidence: Optional[float] = None


class DocumentPageResponse(BaseModel):
    document_id: uuid.UUID
    doc_code: str
    title: str
    source_url: str
    licence: str
    page_number: int
    page_count: int
    chunks: list[PageChunkView]


class IngestRequest(BaseModel):
    file_path: str
    doc_code: str
    title: str
    source_url: str
    licence: str
    org: str = "NASA"
    mission: str = "Unknown"
    version: str = "1.0"


class IngestResponse(BaseModel):
    document_id: uuid.UUID
    doc_code: str
    status: str  # ingested | duplicate
    page_count: int
    section_count: int
    chunk_count: int
    ocr_pages: int


class RetrievalSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    mission: Optional[str] = None
    document_ids: Optional[list[uuid.UUID]] = None
    top_k: int = Field(default=6, ge=1, le=20)


class RetrievedChunkOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    doc_code: str
    document_title: str
    source_url: str
    licence: str
    mission: str
    section_id: Optional[uuid.UUID]
    section_title: str
    section_path: str
    page_number: int
    text: str
    bbox_json: list[BBoxItem]
    dense_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0


class RetrievalSearchResponse(BaseModel):
    request_id: str
    stair_level: str
    results: list[RetrievedChunkOut]
    latency_ms: float


class CitationOut(BaseModel):
    id: Optional[uuid.UUID] = None
    document_id: uuid.UUID
    doc_code: str
    document_title: str
    source_url: str
    licence: str
    section_id: Optional[uuid.UUID] = None
    section: str
    page_number: int
    chunk_id: uuid.UUID
    quote: str
    bbox_json: list[BBoxItem] = Field(default_factory=list)
    verified: bool = True


class ClaimOut(BaseModel):
    claim_text: str
    evidence_classification: EvidenceClassification
    citations: list[CitationOut]


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    conversation_id: Optional[uuid.UUID] = None
    mission: Optional[str] = None
    document_ids: Optional[list[uuid.UUID]] = None


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    retrieval_log_id: uuid.UUID
    answer: str
    claims: list[ClaimOut]
    citations: list[CitationOut]
    confidence: ConfidenceCategory
    confidence_score: float
    evidence_classification: EvidenceClassification
    abstained: bool
    stair_level: str


class CorpusStatsResponse(BaseModel):
    document_count: int
    section_count: int
    chunk_count: int
    ocr_chunk_count: int
    retrieval_log_count: int
    evaluation_status: str = "Not yet evaluated"
