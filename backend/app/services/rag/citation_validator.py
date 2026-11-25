"""Pre-response Citation Validator ensuring every citation maps to a real chunk, page, and quote."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import Document, DocumentChunk, DocumentSection
from app.schemas import CitationOut, ClaimOut, EvidenceClassification
from app.services.retrieval.hybrid import RetrievedCandidate


class LLMCitationRef(BaseModel):
    chunk_id: str
    document_id: Optional[str] = None
    page_number: Optional[int] = None
    quote: str = Field(..., min_length=3)


class LLMClaimItem(BaseModel):
    claim_text: str = Field(..., min_length=4)
    evidence_classification: EvidenceClassification = "explicitly_stated"
    citation_refs: list[LLMCitationRef] = Field(default_factory=list)


class LLMRAGOutput(BaseModel):
    insufficient_evidence: bool = False
    conflicting_evidence: bool = False
    claims: list[LLMClaimItem] = Field(default_factory=list)


@dataclass
class ValidationReport:
    verified_claims: list[ClaimOut]
    verified_citations: list[CitationOut]
    total_raw_citations: int
    valid_citations_count: int
    stripped_citations_count: int
    dropped_claims_count: int
    needs_regeneration: bool

    @property
    def pass_rate(self) -> float:
        if self.total_raw_citations == 0:
            return 0.0
        return round(self.valid_citations_count / self.total_raw_citations, 4)


_STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "this", "were", "was", "are",
    "have", "had", "has", "not", "but", "into", "onto", "its", "their", "which",
}


def _content_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _quote_supported_by_chunk(quote: str, claim_text: str, chunk_text: str) -> bool:
    norm_chunk = _normalize_ws(chunk_text)
    norm_quote = _normalize_ws(quote)
    if norm_quote and len(norm_quote) >= 12 and norm_quote in norm_chunk:
        return True

    # Lexical containment check for slightly elided quotes or paraphrased claims
    quote_tokens = _content_tokens(quote)
    chunk_tokens = _content_tokens(chunk_text)
    if quote_tokens and len(quote_tokens & chunk_tokens) / len(quote_tokens) >= 0.55:
        return True

    claim_tokens = _content_tokens(claim_text)
    if claim_tokens and len(claim_tokens & chunk_tokens) / len(claim_tokens) >= 0.5:
        return True

    return False


def validate_and_filter_claims(
    llm_output: LLMRAGOutput,
    retrieved_candidates: list[RetrievedCandidate],
    db: Optional[Session] = None,
) -> ValidationReport:
    """Validate every citation against real stored chunks & pages before returning."""
    candidate_map: dict[uuid.UUID, RetrievedCandidate] = {
        c.chunk_id: c for c in retrieved_candidates
    }

    verified_claims: list[ClaimOut] = []
    verified_citations: list[CitationOut] = []
    seen_citation_keys: set[tuple[uuid.UUID, int]] = set()

    total_raw = 0
    valid_count = 0
    stripped_count = 0
    dropped_claims = 0

    for claim_idx, item in enumerate(llm_output.claims):
        claim_citations: list[CitationOut] = []
        for ref in item.citation_refs:
            total_raw += 1
            try:
                cid = uuid.UUID(str(ref.chunk_id).strip())
            except ValueError:
                stripped_count += 1
                continue

            resolved = _resolve_chunk(cid, candidate_map, db)
            if resolved is None:
                stripped_count += 1
                continue

            # If LLM supplied document_id or page_number, verify they match the real chunk
            if ref.document_id:
                try:
                    if uuid.UUID(str(ref.document_id).strip()) != resolved.document_id:
                        stripped_count += 1
                        continue
                except ValueError:
                    stripped_count += 1
                    continue

            if ref.page_number is not None and ref.page_number != resolved.page_number:
                stripped_count += 1
                continue

            if not _quote_supported_by_chunk(ref.quote, item.claim_text, resolved.text):
                stripped_count += 1
                continue

            valid_count += 1
            cit = CitationOut(
                document_id=resolved.document_id,
                doc_code=resolved.doc_code,
                document_title=resolved.document_title,
                source_url=resolved.source_url,
                licence=resolved.licence,
                section_id=resolved.section_id,
                section=resolved.section_title,
                page_number=resolved.page_number,
                chunk_id=resolved.chunk_id,
                quote=ref.quote.strip(),
                bbox_json=resolved.bbox_json,
                verified=True,
            )
            claim_citations.append(cit)
            dedupe_key = (resolved.chunk_id, claim_idx)
            if dedupe_key not in seen_citation_keys:
                seen_citation_keys.add(dedupe_key)
                verified_citations.append(cit)

        if claim_citations:
            verified_claims.append(
                ClaimOut(
                    claim_text=item.claim_text.strip(),
                    evidence_classification=item.evidence_classification,
                    citations=claim_citations,
                )
            )
        else:
            dropped_claims += 1

    needs_regen = len(verified_claims) == 0 and (
        len(llm_output.claims) > 0 or stripped_count > 0
    )

    return ValidationReport(
        verified_claims=verified_claims,
        verified_citations=verified_citations,
        total_raw_citations=total_raw,
        valid_citations_count=valid_count,
        stripped_citations_count=stripped_count,
        dropped_claims_count=dropped_claims,
        needs_regeneration=needs_regen,
    )


def _resolve_chunk(
    chunk_id: uuid.UUID,
    candidate_map: dict[uuid.UUID, RetrievedCandidate],
    db: Optional[Session],
) -> Optional[RetrievedCandidate]:
    # Always verify against DB when session is provided so stale/deleted chunks cannot pass
    if db is not None:
        row = db.execute(
            select(DocumentChunk, Document, DocumentSection)
            .join(Document, Document.id == DocumentChunk.document_id)
            .outerjoin(DocumentSection, DocumentSection.id == DocumentChunk.section_id)
            .where(DocumentChunk.id == chunk_id)
        ).first()
        if row is None:
            return None
        chunk, doc, sec = row
        existing = candidate_map.get(chunk_id)
        return RetrievedCandidate(
            chunk_id=chunk.id,
            document_id=doc.id,
            doc_code=doc.doc_code,
            document_title=doc.title,
            source_url=doc.source_url,
            licence=doc.licence,
            mission=doc.mission,
            section_id=sec.id if sec else chunk.section_id,
            section_title=sec.title if sec else "Document Body",
            section_path=sec.section_path if sec else "1",
            page_number=chunk.page_number,
            text=chunk.text,
            bbox_json=list(chunk.bbox_json or []),
            dense_score=existing.dense_score if existing else 0.0,
            bm25_score=existing.bm25_score if existing else 0.0,
            rrf_score=existing.rrf_score if existing else 0.0,
            rerank_score=existing.rerank_score if existing else 0.0,
        )

    return candidate_map.get(chunk_id)
