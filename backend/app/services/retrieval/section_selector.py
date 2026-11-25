"""SectionSelector interface & implementations for STAIR structure-aware retrieval.

Honest STAIR levels (per GEMINI.md Rule 8):
- L1: Hierarchical ToC/section index (`L1PassThroughSectionSelector` or `BM25ToCSectionSelector`).
- L2: ToC-aware query-to-leaf selection via LLM with strict ToC leaf-ID validation (`STAIRInspiredSectionSelector`).
- L3/L4: Fine-tuned LoRA ToC+query -> constrained leaf ID (`FineTunedSTAIRSectionSelector`).
"""

from __future__ import annotations

import logging
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.documents import Document, DocumentChunk, DocumentSection
from app.services.llm.client import LLMClient, get_llm_client

logger = logging.getLogger(__name__)


def _tok(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*", text.lower())


@dataclass
class SelectedSectionMeta:
    section_id: uuid.UUID
    document_id: uuid.UUID
    doc_code: str
    section_path: str
    title: str
    page_start: int
    page_end: int
    reason: str = ""


@dataclass
class SectionSelectionResult:
    stair_level: str
    selector_name: str
    selected_section_ids: Optional[list[uuid.UUID]]
    selected_sections: list[SelectedSectionMeta] = field(default_factory=list)
    invalid_ids_count: int = 0
    total_proposed_ids: int = 0
    used_fallback: bool = False
    stub_not_trained: bool = False


class _STAIRSectionPick(BaseModel):
    section_id: str
    reason: str = ""


class _STAIRSelectionOutput(BaseModel):
    selected_sections: list[_STAIRSectionPick] = Field(default_factory=list)


class SectionSelector(ABC):
    stair_level: str = "L1"
    selector_name: str = "base"

    @abstractmethod
    def select(
        self,
        db: Session,
        query: str,
        document_ids: Optional[list[uuid.UUID]] = None,
        top_k_sections: int = 6,
        allowed_classifications: Optional[list[str]] = None,
    ) -> SectionSelectionResult:
        """Select leaf section IDs from the document ToC for a query."""

    def select_sections(
        self,
        db: Session,
        query: str,
        document_ids: Optional[list[uuid.UUID]] = None,
        top_k_sections: int = 6,
        allowed_classifications: Optional[list[str]] = None,
    ) -> Optional[list[uuid.UUID]]:
        return self.select(
            db=db,
            query=query,
            document_ids=document_ids,
            top_k_sections=top_k_sections,
            allowed_classifications=allowed_classifications,
        ).selected_section_ids


def _load_toc_rows(
    db: Session,
    document_ids: Optional[list[uuid.UUID]] = None,
    allowed_classifications: Optional[list[str]] = None,
) -> list[tuple[DocumentSection, Document]]:
    stmt = (
        select(DocumentSection, Document)
        .join(Document, Document.id == DocumentSection.document_id)
        .order_by(Document.doc_code.asc(), DocumentSection.order_index.asc())
    )
    if document_ids:
        stmt = stmt.where(DocumentSection.document_id.in_(document_ids))
    if allowed_classifications:
        stmt = stmt.where(Document.classification.in_(allowed_classifications))
    return list(db.execute(stmt).all())


class L1PassThroughSectionSelector(SectionSelector):
    """Phase 1 baseline: uses L1 hierarchical index metadata without leaf pruning."""

    stair_level = "L1"
    selector_name = "l1_passthrough"

    def select(
        self,
        db: Session,
        query: str,
        document_ids: Optional[list[uuid.UUID]] = None,
        top_k_sections: int = 6,
        allowed_classifications: Optional[list[str]] = None,
    ) -> SectionSelectionResult:
        return SectionSelectionResult(
            stair_level=self.stair_level,
            selector_name=self.selector_name,
            selected_section_ids=None,
        )


class BM25ToCSectionSelector(SectionSelector):
    """(a) BM25-over-ToC baseline: ranks leaf sections by BM25 over title, path & lead snippet."""

    stair_level = "L1-BM25"
    selector_name = "bm25_toc"

    def select(
        self,
        db: Session,
        query: str,
        document_ids: Optional[list[uuid.UUID]] = None,
        top_k_sections: int = 6,
        allowed_classifications: Optional[list[str]] = None,
    ) -> SectionSelectionResult:
        rows = _load_toc_rows(db, document_ids, allowed_classifications=allowed_classifications)
        leaf_rows = [(sec, doc) for sec, doc in rows if sec.is_leaf]
        if not leaf_rows:
            leaf_rows = rows
        if not leaf_rows:
            return SectionSelectionResult(
                stair_level=self.stair_level,
                selector_name=self.selector_name,
                selected_section_ids=None,
            )

        # Fetch first chunk text per leaf section for richer ToC keyword matching
        leaf_ids = [sec.id for sec, _ in leaf_rows]
        first_chunk_subq = (
            select(
                DocumentChunk.section_id,
                func.min(DocumentChunk.chunk_index).label("min_idx"),
            )
            .where(DocumentChunk.section_id.in_(leaf_ids))
            .group_by(DocumentChunk.section_id)
            .subquery()
        )
        lead_texts: dict[uuid.UUID, str] = {}
        lead_rows = db.execute(
            select(DocumentChunk.section_id, DocumentChunk.text).join(
                first_chunk_subq,
                (DocumentChunk.section_id == first_chunk_subq.c.section_id)
                & (DocumentChunk.chunk_index == first_chunk_subq.c.min_idx),
            )
        ).all()
        for sid, txt in lead_rows:
            if sid:
                lead_texts[sid] = txt[:320]

        corpus_tokens = [
            _tok(
                f"{doc.mission} {doc.doc_code} {sec.section_path} {sec.title} {lead_texts.get(sec.id, '')}"
            )
            for sec, doc in leaf_rows
        ]
        query_tokens = _tok(query)
        if not query_tokens or not any(corpus_tokens):
            return SectionSelectionResult(
                stair_level=self.stair_level,
                selector_name=self.selector_name,
                selected_section_ids=None,
            )

        bm25 = BM25Okapi(corpus_tokens)
        bm25_scores = bm25.get_scores(query_tokens)
        q_set = set(query_tokens)
        combined_scores: list[float] = []
        for doc_tokens, raw_bm25 in zip(corpus_tokens, bm25_scores, strict=True):
            overlap = len(q_set & set(doc_tokens)) / max(1, len(q_set))
            # Combine BM25 with lexical overlap so small ToCs (N=2..4) with IDF<=0 still rank matches
            score = max(0.0, float(raw_bm25)) + (0.25 * overlap if overlap > 0 else 0.0)
            combined_scores.append(score)

        ranked = sorted(
            zip(leaf_rows, combined_scores, strict=True),
            key=lambda pair: float(pair[1]),
            reverse=True,
        )
        positive = [(sec, doc, float(sc)) for (sec, doc), sc in ranked if float(sc) > 0.0]
        chosen = positive[:top_k_sections]
        if not chosen:
            return SectionSelectionResult(
                stair_level=self.stair_level,
                selector_name=self.selector_name,
                selected_section_ids=None,
            )

        metas = [
            SelectedSectionMeta(
                section_id=sec.id,
                document_id=doc.id,
                doc_code=doc.doc_code,
                section_path=sec.section_path,
                title=sec.title,
                page_start=sec.page_start,
                page_end=sec.page_end,
                reason=f"BM25-ToC score={sc:.2f}",
            )
            for sec, doc, sc in chosen
        ]
        return SectionSelectionResult(
            stair_level=self.stair_level,
            selector_name=self.selector_name,
            selected_section_ids=[m.section_id for m in metas],
            selected_sections=metas,
            total_proposed_ids=len(metas),
        )


class STAIRInspiredSectionSelector(SectionSelector):
    """(b) STAIR L2 selector: ToC + query prompt -> validated top-k leaf section IDs."""

    stair_level = "L2"
    selector_name = "stair_l2"

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm_client = llm_client
        self._fallback = BM25ToCSectionSelector()

    def select(
        self,
        db: Session,
        query: str,
        document_ids: Optional[list[uuid.UUID]] = None,
        top_k_sections: int = 6,
        allowed_classifications: Optional[list[str]] = None,
    ) -> SectionSelectionResult:
        rows = _load_toc_rows(db, document_ids, allowed_classifications=allowed_classifications)
        if not rows:
            return SectionSelectionResult(
                stair_level=self.stair_level,
                selector_name=self.selector_name,
                selected_section_ids=None,
            )

        valid_leaf_map: dict[uuid.UUID, tuple[DocumentSection, Document]] = {
            sec.id: (sec, doc) for sec, doc in rows if sec.is_leaf
        }
        if not valid_leaf_map:
            valid_leaf_map = {sec.id: (sec, doc) for sec, doc in rows}

        # Format hierarchical ToC with explicit leaf IDs (capped for prompt budget)
        toc_lines: list[str] = []
        current_doc_id: Optional[uuid.UUID] = None
        for sec, doc in rows[:450]:
            if doc.id != current_doc_id:
                current_doc_id = doc.id
                toc_lines.append(f"\n=== DOCUMENT {doc.doc_code}: {doc.title} ({doc.mission}) ===")
            indent = "  " * max(0, sec.level - 1)
            if sec.id in valid_leaf_map:
                toc_lines.append(
                    f"{indent}- [LEAF id={sec.id}] §{sec.section_path} {sec.title} (pp.{sec.page_start}-{sec.page_end})"
                )
            else:
                toc_lines.append(
                    f"{indent}- [NODE] §{sec.section_path} {sec.title} (pp.{sec.page_start}-{sec.page_end})"
                )

        settings = get_settings()
        if self._llm_client is None and not settings.gemini_api_key:
            fb = self._fallback.select(db, query, document_ids, top_k_sections)
            fb.used_fallback = True
            return fb

        client = self._llm_client or get_llm_client()
        system_prompt = (
            "You are a STAIR L2 structure-aware section selector. Given a user query and hierarchical "
            "mission-report Tables of Contents, return JSON selecting up to K LEAF section_ids most likely "
            "to contain the answer. ONLY select IDs marked [LEAF id=...]. Never invent UUIDs."
        )
        user_prompt = (
            f"USER QUERY: {query.strip()}\n"
            f"MAX SECTIONS K: {top_k_sections}\n\n"
            f"TABLE OF CONTENTS:\n" + "\n".join(toc_lines)
        )

        try:
            llm_out = client.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_cls=_STAIRSelectionOutput,
                max_retries=1,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("STAIR L2 LLM selection failed, falling back to BM25-ToC: %s", exc)
            fb = self._fallback.select(db, query, document_ids, top_k_sections)
            fb.used_fallback = True
            return fb

        selected_metas: list[SelectedSectionMeta] = []
        seen_ids: set[uuid.UUID] = set()
        invalid_count = 0
        total_proposed = len(llm_out.selected_sections)

        for pick in llm_out.selected_sections:
            try:
                sid = uuid.UUID(str(pick.section_id).strip())
            except ValueError:
                invalid_count += 1
                continue

            if sid not in valid_leaf_map:
                invalid_count += 1
                continue

            if sid in seen_ids:
                continue
            seen_ids.add(sid)

            sec, doc = valid_leaf_map[sid]
            selected_metas.append(
                SelectedSectionMeta(
                    section_id=sec.id,
                    document_id=doc.id,
                    doc_code=doc.doc_code,
                    section_path=sec.section_path,
                    title=sec.title,
                    page_start=sec.page_start,
                    page_end=sec.page_end,
                    reason=pick.reason.strip(),
                )
            )
            if len(selected_metas) >= top_k_sections:
                break

        if not selected_metas:
            fb = self._fallback.select(db, query, document_ids, top_k_sections)
            fb.invalid_ids_count = invalid_count
            fb.total_proposed_ids = total_proposed
            fb.used_fallback = True
            return fb

        return SectionSelectionResult(
            stair_level=self.stair_level,
            selector_name=self.selector_name,
            selected_section_ids=[m.section_id for m in selected_metas],
            selected_sections=selected_metas,
            invalid_ids_count=invalid_count,
            total_proposed_ids=total_proposed,
            used_fallback=False,
        )


class FineTunedSTAIRSectionSelector(SectionSelector):
    """(c) Stub for fine-tuned LoRA STAIR L3/L4 model (constrained leaf-ID decoding).

    When STAIR_LORA_ADAPTER_PATH points to a trained LoRA checkpoint on disk, loads it;
    otherwise returns honest stub status and delegates to fallback without blocking the app.
    """

    stair_level = "L3"
    selector_name = "stair_lora_l3"

    def __init__(
        self,
        adapter_path: Optional[str] = None,
        fallback_selector: Optional[SectionSelector] = None,
    ) -> None:
        settings = get_settings()
        self.adapter_path = Path(adapter_path or settings.stair_lora_adapter_path) if (
            adapter_path or settings.stair_lora_adapter_path
        ) else None
        self.fallback = fallback_selector or BM25ToCSectionSelector()

    def is_trained_model_available(self) -> bool:
        return bool(self.adapter_path and self.adapter_path.exists())

    def select(
        self,
        db: Session,
        query: str,
        document_ids: Optional[list[uuid.UUID]] = None,
        top_k_sections: int = 6,
        allowed_classifications: Optional[list[str]] = None,
    ) -> SectionSelectionResult:
        if not self.is_trained_model_available():
            logger.info(
                "STAIR L3 LoRA adapter not present (%s); using non-blocking fallback.",
                self.adapter_path,
            )
            res = self.fallback.select(
                db,
                query,
                document_ids,
                top_k_sections,
                allowed_classifications=allowed_classifications,
            )
            res.used_fallback = True
            res.stub_not_trained = True
            return res

        # Runtime hook for trained PEFT LoRA adapter (see scripts/train_stair.py)
        # Falls back cleanly if optional GPU/peft runtime dependencies are not installed
        try:
            from scripts.train_stair import predict_leaf_sections_with_lora  # type: ignore

            rows = _load_toc_rows(db, document_ids, allowed_classifications=allowed_classifications)
            valid_leaf_map = {sec.id: (sec, doc) for sec, doc in rows if sec.is_leaf}
            predicted_ids = predict_leaf_sections_with_lora(
                adapter_path=str(self.adapter_path),
                query=query,
                toc_rows=rows,
                top_k=top_k_sections,
            )
            metas: list[SelectedSectionMeta] = []
            invalid = 0
            for raw_id in predicted_ids:
                try:
                    uid = uuid.UUID(str(raw_id))
                    if uid in valid_leaf_map:
                        sec, doc = valid_leaf_map[uid]
                        metas.append(
                            SelectedSectionMeta(
                                section_id=sec.id,
                                document_id=doc.id,
                                doc_code=doc.doc_code,
                                section_path=sec.section_path,
                                title=sec.title,
                                page_start=sec.page_start,
                                page_end=sec.page_end,
                                reason="STAIR L3 LoRA constrained decoding",
                            )
                        )
                    else:
                        invalid += 1
                except ValueError:
                    invalid += 1
            if metas:
                return SectionSelectionResult(
                    stair_level="L3",
                    selector_name="stair_lora_l3",
                    selected_section_ids=[m.section_id for m in metas],
                    selected_sections=metas,
                    invalid_ids_count=invalid,
                    total_proposed_ids=len(predicted_ids),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("STAIR L3 inference unavailable, using fallback: %s", exc)

        res = self.fallback.select(db, query, document_ids, top_k_sections)
        res.used_fallback = True
        return res


def build_section_selector(
    mode: Optional[str] = None,
    llm_client: Optional[LLMClient] = None,
) -> SectionSelector:
    settings = get_settings()
    chosen = (mode or settings.section_selector_mode or "auto").lower().strip()

    if chosen == "l1_passthrough":
        return L1PassThroughSectionSelector()
    if chosen == "bm25_toc":
        return BM25ToCSectionSelector()
    if chosen == "stair_l2":
        return STAIRInspiredSectionSelector(llm_client=llm_client)
    if chosen == "stair_l3":
        return FineTunedSTAIRSectionSelector()

    # "auto": use STAIR L2 if Gemini key configured, else BM25-over-ToC baseline
    if settings.gemini_api_key or llm_client is not None:
        return STAIRInspiredSectionSelector(llm_client=llm_client)
    return BM25ToCSectionSelector()
