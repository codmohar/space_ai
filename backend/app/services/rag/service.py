"""Shared RAG orchestrator used by /api/chat and downstream services."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.config import ABSTENTION_MESSAGE, get_settings
from app.core.errors import ApiError
from app.models.rag import Citation, Conversation, Message
from app.schemas import ChatResponse, ClaimOut, EvidenceClassification, SelectedSectionOut
from app.services.llm.client import LLMClient, get_llm_client
from app.services.rag.citation_validator import (
    LLMRAGOutput,
    validate_and_filter_claims,
)
from app.services.rag.confidence import compute_retrieval_confidence
from app.services.rag.prompt_guard import GROUNDED_SYSTEM_PROMPT, build_grounded_user_prompt
from app.services.rag.query_rewriter import rewrite_followup_query
from app.services.rag.spoken_formatter import format_spoken_answer
from app.services.retrieval.hybrid import HybridRetriever, RetrievedCandidate
from app.services.retrieval.logger import record_retrieval_log
from app.services.retrieval.section_selector import build_section_selector


@dataclass
class RAGExecutionResult:
    answer: str
    claims: list[ClaimOut]
    citations: list
    confidence: str
    confidence_score: float
    evidence_classification: EvidenceClassification
    abstained: bool
    stair_level: str
    retrieval_log_id: uuid.UUID
    selector_name: str = "l1_passthrough"
    selected_sections: list[SelectedSectionOut] = field(default_factory=list)
    used_section_ids: list[uuid.UUID] = field(default_factory=list)


class RAGService:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.settings = get_settings()
        self.retriever = retriever
        self._llm_client = llm_client

    def _get_llm(self) -> LLMClient:
        return self._llm_client or get_llm_client()

    def _get_retriever(self, selector_mode: Optional[str] = None) -> HybridRetriever:
        if self.retriever is not None and not selector_mode:
            return self.retriever
        selector = build_section_selector(mode=selector_mode, llm_client=self._llm_client)
        return HybridRetriever(section_selector=selector)

    def answer_query(
        self,
        db: Session,
        query: str,
        request_id: str,
        mission: Optional[str] = None,
        document_ids: Optional[list[uuid.UUID]] = None,
        selector_mode: Optional[str] = None,
        simpler: bool = False,
        allowed_classifications: Optional[list[str]] = None,
    ) -> RAGExecutionResult:
        retriever = self._get_retriever(selector_mode)
        candidates, telemetry = retriever.search(
            db=db,
            query=query,
            mission=mission,
            document_ids=document_ids,
            allowed_classifications=allowed_classifications,
        )

        selected_sections = [
            SelectedSectionOut(
                section_id=uuid.UUID(s["section_id"]),
                document_id=uuid.UUID(s["document_id"]),
                doc_code=s["doc_code"],
                section_path=s["section_path"],
                title=s["title"],
                page_start=s["page_start"],
                page_end=s["page_end"],
                reason=s.get("reason", ""),
            )
            for s in telemetry.get("selected_sections", [])
        ]
        selector_name = telemetry.get("selector_name", "l1_passthrough")

        top_rerank = telemetry.get("top_rerank_score", 0.0)
        top_rrf = telemetry.get("top_rrf_score", 0.0)

        # Evidence sufficiency gate before calling LLM
        if (
            not candidates
            or top_rerank < self.settings.min_rerank_score_threshold
            or top_rrf < self.settings.min_rrf_score_threshold
        ):
            conf_cat = "None" if not candidates else "Insufficient"
            log = record_retrieval_log(
                db=db,
                request_id=request_id,
                query_text=query,
                mission_scope=mission,
                telemetry=telemetry,
                confidence_category=conf_cat,
                abstained=True,
                llm_model=None,
            )
            return RAGExecutionResult(
                answer=ABSTENTION_MESSAGE,
                claims=[],
                citations=[],
                confidence=conf_cat,
                confidence_score=0.0 if not candidates else round(top_rerank, 3),
                evidence_classification="unknown",
                abstained=True,
                stair_level=telemetry.get("stair_level", "L1"),
                retrieval_log_id=log.id,
                selector_name=selector_name,
                selected_sections=selected_sections,
                used_section_ids=[],
            )

        llm = self._get_llm()
        user_prompt = build_grounded_user_prompt(
            query, candidates, strict_retry=False, simpler=simpler
        )
        try:
            llm_out = llm.generate_structured(
                system_prompt=GROUNDED_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema_cls=LLMRAGOutput,
                max_retries=self.settings.llm_max_retries,
            )
        except ApiError as exc:
            if exc.code == "LLM_GENERATION_FAILED" and candidates:
                logger.warning("LLM generation failed (quota/upstream). Using extractive grounded fallback: %s", exc)
                llm_out = self._extractive_grounded_fallback(query, candidates)
            else:
                raise

        if llm_out.insufficient_evidence or not llm_out.claims:
            log = record_retrieval_log(
                db=db,
                request_id=request_id,
                query_text=query,
                mission_scope=mission,
                telemetry=telemetry,
                confidence_category="Insufficient",
                abstained=True,
                llm_model=llm.model_name,
            )
            return RAGExecutionResult(
                answer=ABSTENTION_MESSAGE,
                claims=[],
                citations=[],
                confidence="Insufficient",
                confidence_score=round(min(0.35, top_rerank), 3),
                evidence_classification="unknown",
                abstained=True,
                stair_level=telemetry.get("stair_level", "L1"),
                retrieval_log_id=log.id,
                selector_name=selector_name,
                selected_sections=selected_sections,
                used_section_ids=[],
            )

        validation = validate_and_filter_claims(llm_out, candidates, db=db)

        if validation.needs_regeneration:
            retry_prompt = build_grounded_user_prompt(query, candidates, strict_retry=True)
            llm_out_retry = llm.generate_structured(
                system_prompt=GROUNDED_SYSTEM_PROMPT,
                user_prompt=retry_prompt,
                schema_cls=LLMRAGOutput,
                max_retries=self.settings.llm_max_retries,
            )
            if not llm_out_retry.insufficient_evidence and llm_out_retry.claims:
                validation = validate_and_filter_claims(llm_out_retry, candidates, db=db)
                llm_out = llm_out_retry

        if not validation.verified_claims:
            log = record_retrieval_log(
                db=db,
                request_id=request_id,
                query_text=query,
                mission_scope=mission,
                telemetry=telemetry,
                confidence_category="Insufficient",
                abstained=True,
                llm_model=llm.model_name,
            )
            return RAGExecutionResult(
                answer=ABSTENTION_MESSAGE,
                claims=[],
                citations=[],
                confidence="Insufficient",
                confidence_score=0.0,
                evidence_classification="unknown",
                abstained=True,
                stair_level=telemetry.get("stair_level", "L1"),
                retrieval_log_id=log.id,
                selector_name=selector_name,
                selected_sections=selected_sections,
                used_section_ids=[],
            )

        cand_score_map: dict[uuid.UUID, RetrievedCandidate] = {c.chunk_id: c for c in candidates}
        cited_scores = [
            cand_score_map[c.chunk_id].rerank_score
            for c in validation.verified_citations
            if c.chunk_id in cand_score_map
        ]
        mean_cited = sum(cited_scores) / len(cited_scores) if cited_scores else top_rerank

        conf_category, conf_score = compute_retrieval_confidence(
            top_rerank_score=top_rerank,
            mean_cited_rerank_score=mean_cited,
            citation_pass_rate=validation.pass_rate,
            verified_claim_count=len(validation.verified_claims),
            dropped_claim_count=validation.dropped_claims_count,
            has_conflicting_evidence=llm_out.conflicting_evidence,
            min_rerank_threshold=self.settings.min_rerank_score_threshold,
        )

        answer_lines: list[str] = []
        for claim in validation.verified_claims:
            chips = " ".join(
                f"[{cit.doc_code} · p.{cit.page_number} · {cit.section}]"
                for cit in claim.citations
            )
            answer_lines.append(f"{claim.claim_text} {chips}")
        answer_text = "\n\n".join(answer_lines)

        dominant_class = _dominant_classification(validation.verified_claims)
        used_sec_ids = list(
            dict.fromkeys(
                cit.section_id
                for cit in validation.verified_citations
                if cit.section_id is not None
            )
        )

        log = record_retrieval_log(
            db=db,
            request_id=request_id,
            query_text=query,
            mission_scope=mission,
            telemetry={
                **telemetry,
                "citation_pass_rate": validation.pass_rate,
                "stripped_citations": validation.stripped_citations_count,
                "dropped_claims": validation.dropped_claims_count,
            },
            confidence_category=conf_category,
            abstained=False,
            llm_model=llm.model_name,
        )

        return RAGExecutionResult(
            answer=answer_text,
            claims=validation.verified_claims,
            citations=validation.verified_citations,
            confidence=conf_category,
            confidence_score=conf_score,
            evidence_classification=dominant_class,
            abstained=False,
            stair_level=telemetry.get("stair_level", "L1"),
            retrieval_log_id=log.id,
            selector_name=selector_name,
            selected_sections=selected_sections,
            used_section_ids=used_sec_ids,
        )

    def chat_and_persist(
        self,
        db: Session,
        query: str,
        request_id: str,
        conversation_id: Optional[uuid.UUID] = None,
        mission: Optional[str] = None,
        document_ids: Optional[list[uuid.UUID]] = None,
        selector_mode: Optional[str] = None,
        allowed_classifications: Optional[list[str]] = None,
    ) -> ChatResponse:
        conv: Conversation | None = None
        if conversation_id is not None:
            conv = db.get(Conversation, conversation_id)

        if conv is None:
            conv = Conversation(
                id=uuid.uuid4(),
                title=query.strip()[:80] or "Mission Inquiry",
                mission_scope=mission,
            )
            db.add(conv)
            db.flush()

        # Load conversation memory before inserting the new user message
        history: list[tuple[str, str]] = []
        all_msgs: list[Message] = []
        if conv.id is not None:
            all_msgs = list(
                db.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.asc())
                )
                .scalars()
                .all()
            )
            history = [(m.role, m.content) for m in all_msgs[-6:]]

        # Dynamic mission names from database
        db_missions = list(
            db.execute(select(Document.mission).distinct()).scalars().all()
        )

        rewritten = rewrite_followup_query(
            query=query,
            history=history,
            mission_scope=mission or conv.mission_scope,
            conversation_summary=conv.summary,
            known_missions=db_missions,
            llm_client=self._llm_client,
        )

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=query.strip(),
        )
        db.add(user_msg)
        db.flush()

        rag_res = self.answer_query(
            db=db,
            query=rewritten.standalone_query,
            request_id=request_id,
            mission=rewritten.resolved_mission or mission,
            document_ids=document_ids,
            selector_mode=selector_mode,
            simpler=rewritten.response_style == "simpler",
            allowed_classifications=allowed_classifications,
        )

        spoken_text = format_spoken_answer(
            claims=rag_res.claims,
            abstained=rag_res.abstained,
            written_answer=rag_res.answer,
            style=rewritten.response_style,
        )

        assistant_msg = Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            retrieval_log_id=rag_res.retrieval_log_id,
            role="assistant",
            content=rag_res.answer,
            confidence=rag_res.confidence,
            confidence_score=rag_res.confidence_score,
            abstained=rag_res.abstained,
            claims_json=[c.model_dump(mode="json") for c in rag_res.claims],
        )
        db.add(assistant_msg)
        db.flush()

        # Rolling summary update after 4+ turns
        from app.services.rag.summarizer import build_rolling_summary

        total_turns = len(all_msgs) + 2
        if total_turns >= 4 and total_turns % 2 == 0:
            updated_history = [(m.role, m.content) for m in (all_msgs + [user_msg, assistant_msg])]
            conv.summary = build_rolling_summary(
                messages=updated_history[-10:],
                existing_summary=conv.summary,
                mission_scope=conv.mission_scope,
                llm_client=self._llm_client,
            )
            db.add(conv)
            db.flush()

        persisted_citations = []
        for idx, claim in enumerate(rag_res.claims):
            for cit in claim.citations:
                db_cit = Citation(
                    message_id=assistant_msg.id,
                    document_id=cit.document_id,
                    section_id=cit.section_id,
                    chunk_id=cit.chunk_id,
                    page_number=cit.page_number,
                    claim_index=idx,
                    evidence_classification=claim.evidence_classification,
                    evidence_text=cit.quote,
                    verified=cit.verified,
                )
                db.add(db_cit)
                db.flush()
                cit.id = db_cit.id
                persisted_citations.append(cit)

        db.commit()

        return ChatResponse(
            conversation_id=conv.id,
            message_id=assistant_msg.id,
            retrieval_log_id=rag_res.retrieval_log_id,
            answer=rag_res.answer,
            spoken_text=spoken_text,
            standalone_query=rewritten.standalone_query,
            response_style=rewritten.response_style,
            claims=rag_res.claims,
            citations=persisted_citations if persisted_citations else rag_res.citations,
            confidence=rag_res.confidence,  # type: ignore[arg-type]
            confidence_score=rag_res.confidence_score,
            evidence_classification=rag_res.evidence_classification,
            abstained=rag_res.abstained,
            stair_level=rag_res.stair_level,
            selector_name=rag_res.selector_name,
            selected_sections=rag_res.selected_sections,
            used_section_ids=rag_res.used_section_ids,
        )

    def _extractive_grounded_fallback(
        self,
        query: str,
        candidates: Sequence[RetrievedCandidate],
    ) -> LLMRAGOutput:
        """Deterministic extractive grounded claims fallback when LLM API quota is exhausted."""
        from app.services.rag.citation_validator import LLMCitationRef, LLMClaimItem

        claims: list[LLMClaimItem] = []
        for cand in candidates[:3]:
            # Pick first 1-2 sentences from candidate chunk text as grounded claim
            sentences = [s.strip() for s in (cand.text or "").split(". ") if len(s.strip()) > 30]
            if not sentences:
                continue
            claim_text = sentences[0]
            if not claim_text.endswith("."):
                claim_text += "."
            quote = claim_text[:120]
            claims.append(
                LLMClaimItem(
                    claim_text=claim_text,
                    evidence_classification="explicitly_stated",
                    citation_refs=[
                        LLMCitationRef(
                            chunk_id=str(cand.chunk_id),
                            page_number=cand.page_number,
                            quote=quote,
                        )
                    ],
                )
            )

        return LLMRAGOutput(
            claims=claims,
            insufficient_evidence=len(claims) == 0,
            conflicting_evidence=False,
        )


def _dominant_classification(claims: list[ClaimOut]) -> EvidenceClassification:
    priority: list[EvidenceClassification] = [
        "official_root_cause",
        "official_contributing_factor",
        "explicitly_stated",
        "system_inference",
        "unknown",
    ]
    present = {c.evidence_classification for c in claims}
    for item in priority:
        if item in present:
            return item
    return "explicitly_stated"
