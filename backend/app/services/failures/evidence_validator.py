"""Evidence validator for FailureEvents and FailureRelationships.

Rule 6:
- Every event and relationship starts with verification_status='pending'.
- Only promote an event to 'verified' when chunk_id resolves to a real chunk in the
  same document and the evidence quote exists in that chunk's stored text.
- Only promote a relationship to 'verified' when:
  (1) relationship_type is valid,
  (2) evidence_chunk_id resolves to a real chunk in the document and contains the quote, AND
  (3) BOTH source_event and target_event are verified.
"""

from __future__ import annotations

import re
import uuid
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import DocumentChunk
from app.models.failure_kg import FailureEvent, FailureRelationship

ALLOWED_RELATIONSHIP_TYPES = {
    "caused_by",
    "contributed_to",
    "preceded_by",
    "associated_with",
    "reported_as",
}

_STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "this", "were", "was", "are",
    "have", "had", "has", "not", "but", "into", "onto", "its", "their", "which",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _content_tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) >= 3 and t not in _STOPWORDS
    }


def verify_quote_in_chunk(quote: str, chunk_text: str) -> bool:
    """Verify verbatim substring or high lexical containment inside the stored chunk text."""
    norm_quote = _normalize(quote)
    norm_chunk = _normalize(chunk_text)
    if not norm_quote or not norm_chunk:
        return False

    if len(norm_quote) >= 10 and norm_quote in norm_chunk:
        return True

    q_tokens = _content_tokens(quote)
    c_tokens = _content_tokens(chunk_text)
    if not q_tokens:
        return False

    overlap = len(q_tokens & c_tokens)
    return (overlap / len(q_tokens)) >= 0.70 and overlap >= min(3, len(q_tokens))


def validate_failure_chain_records(
    db: Session,
    document_id: uuid.UUID,
    events: list[FailureEvent],
    relationships: list[FailureRelationship],
    chunk_text_map: Mapping[uuid.UUID, tuple[uuid.UUID, int, str]] | None = None,
) -> tuple[int, int]:
    """Validate events and relationships against stored chunks; return (verified_events, verified_rels)."""
    if chunk_text_map is None:
        needed_ids = {
            *(e.chunk_id for e in events),
            *(r.evidence_chunk_id for r in relationships),
        }
        loaded: dict[uuid.UUID, tuple[uuid.UUID, int, str]] = {}
        if needed_ids:
            rows = db.execute(
                select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.page_number, DocumentChunk.text)
                .where(DocumentChunk.id.in_(list(needed_ids)))
            ).all()
            for cid, did, page_num, txt in rows:
                loaded[cid] = (did, page_num, txt)
        chunk_lookup = loaded
    else:
        chunk_lookup = dict(chunk_text_map)

    event_by_id: dict[uuid.UUID, FailureEvent] = {}
    verified_events_count = 0

    for ev in events:
        event_by_id[ev.id] = ev
        chunk_info = chunk_lookup.get(ev.chunk_id)
        if chunk_info is None:
            ev.verification_status = "pending"
            continue

        chunk_doc_id, chunk_page, chunk_text = chunk_info
        if chunk_doc_id != document_id or chunk_page != ev.page_number:
            ev.verification_status = "pending"
            continue

        if verify_quote_in_chunk(ev.evidence_text, chunk_text):
            ev.verification_status = "verified"
            verified_events_count += 1
        else:
            ev.verification_status = "pending"

    verified_rels_count = 0
    for rel in relationships:
        if rel.relationship_type not in ALLOWED_RELATIONSHIP_TYPES:
            rel.verification_status = "rejected"
            continue

        src = event_by_id.get(rel.source_event_id)
        tgt = event_by_id.get(rel.target_event_id)
        if (
            src is None
            or tgt is None
            or src.verification_status != "verified"
            or tgt.verification_status != "verified"
        ):
            rel.verification_status = "pending"
            continue

        chunk_info = chunk_lookup.get(rel.evidence_chunk_id)
        if chunk_info is None:
            rel.verification_status = "pending"
            continue

        chunk_doc_id, chunk_page, chunk_text = chunk_info
        if (
            chunk_doc_id == document_id
            and chunk_page == rel.page_number
            and verify_quote_in_chunk(rel.evidence_text, chunk_text)
        ):
            rel.verification_status = "verified"
            verified_rels_count += 1
        else:
            rel.verification_status = "pending"

    return verified_events_count, verified_rels_count
