"""Tests for exact abstention behavior and deterministic confidence calculation."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.core.config import ABSTENTION_MESSAGE
from app.services.llm.client import LLMClient
from app.services.rag.citation_validator import LLMCitationRef, LLMClaimItem, LLMRAGOutput
from app.services.rag.confidence import compute_retrieval_confidence
from app.services.rag.service import RAGService
from app.services.retrieval.hybrid import RetrievedCandidate


class _StubLLM(LLMClient):
    model_name = "stub-llm"

    def __init__(self, responses: list[LLMRAGOutput]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def generate_structured(self, system_prompt, user_prompt, schema_cls, max_retries=2):
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]


def _make_candidate(rerank_score: float) -> RetrievedCandidate:
    return RetrievedCandidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_code="NASA-A13-1970",
        document_title="Report of Apollo 13 Review Board",
        source_url="https://ntrs.nasa.gov/api/citations/19700076776/downloads/19700076776.pdf",
        licence="Public Domain (U.S. Government Work - NASA)",
        mission="Apollo 13",
        section_id=uuid.uuid4(),
        section_title="Chapter 4 Summary",
        section_path="4.1",
        page_number=12,
        text="Cryogenic oxygen tank No. 2 experienced an electrical short in the fan wiring during tank stir.",
        bbox_json=[],
        dense_score=0.81,
        bm25_score=6.4,
        rrf_score=0.031,
        rerank_score=rerank_score,
    )


def test_empty_retrieval_returns_exact_abstention_message(monkeypatch) -> None:
    fake_retriever = MagicMock()
    fake_retriever.search.return_value = (
        [],
        {"stair_level": "L1", "top_rerank_score": 0.0, "top_rrf_score": 0.0, "total_ms": 5.0},
    )
    monkeypatch.setattr(
        "app.services.rag.service.record_retrieval_log",
        lambda **kwargs: MagicMock(id=uuid.uuid4()),
    )

    llm = _StubLLM([])
    service = RAGService(retriever=fake_retriever, llm_client=llm)
    res = service.answer_query(db=MagicMock(), query="What was JWST mirror cryo test date?", request_id="req-1")

    assert res.abstained is True
    assert res.answer == ABSTENTION_MESSAGE
    assert res.confidence == "None"
    assert res.claims == []
    assert res.citations == []
    assert llm.calls == 0


def test_low_rerank_score_returns_exact_abstention_message(monkeypatch) -> None:
    cand = _make_candidate(rerank_score=0.05)
    fake_retriever = MagicMock()
    fake_retriever.search.return_value = (
        [cand],
        {"stair_level": "L1", "top_rerank_score": 0.05, "top_rrf_score": 0.031, "total_ms": 11.0},
    )
    monkeypatch.setattr(
        "app.services.rag.service.record_retrieval_log",
        lambda **kwargs: MagicMock(id=uuid.uuid4()),
    )

    llm = _StubLLM([])
    service = RAGService(retriever=fake_retriever, llm_client=llm)
    res = service.answer_query(db=MagicMock(), query="Unrelated orbital debris treaty?", request_id="req-2")

    assert res.abstained is True
    assert res.answer == ABSTENTION_MESSAGE
    assert res.confidence == "Insufficient"
    assert llm.calls == 0


def test_all_fabricated_citations_triggers_retry_then_abstention(monkeypatch) -> None:
    cand = _make_candidate(rerank_score=0.86)
    fake_retriever = MagicMock()
    fake_retriever.search.return_value = (
        [cand],
        {"stair_level": "L1", "top_rerank_score": 0.86, "top_rrf_score": 0.031, "total_ms": 18.0},
    )
    monkeypatch.setattr(
        "app.services.rag.service.record_retrieval_log",
        lambda **kwargs: MagicMock(id=uuid.uuid4()),
    )

    bad_output = LLMRAGOutput(
        claims=[
            LLMClaimItem(
                claim_text="Fabricated claim.",
                evidence_classification="explicitly_stated",
                citation_refs=[
                    LLMCitationRef(chunk_id=str(uuid.uuid4()), page_number=12, quote="fabricated quote text")
                ],
            )
        ]
    )
    llm = _StubLLM([bad_output, bad_output])
    # Mock DB session so _resolve_chunk returns None for fabricated UUID
    mock_db = MagicMock()
    mock_db.execute.return_value.first.return_value = None

    service = RAGService(retriever=fake_retriever, llm_client=llm)
    res = service.answer_query(db=mock_db, query="What failed in Apollo 13?", request_id="req-3")

    assert llm.calls == 2
    assert res.abstained is True
    assert res.answer == ABSTENTION_MESSAGE
    assert res.confidence == "Insufficient"


def test_deterministic_confidence_categories() -> None:
    cat_strong, score_strong = compute_retrieval_confidence(
        top_rerank_score=0.92,
        mean_cited_rerank_score=0.88,
        citation_pass_rate=1.0,
        verified_claim_count=3,
        dropped_claim_count=0,
    )
    assert cat_strong == "Strong"
    assert score_strong >= 0.72

    cat_partial, _ = compute_retrieval_confidence(
        top_rerank_score=0.55,
        mean_cited_rerank_score=0.45,
        citation_pass_rate=0.5,
        verified_claim_count=1,
        dropped_claim_count=1,
    )
    assert cat_partial == "Partial"

    cat_conflict, _ = compute_retrieval_confidence(
        top_rerank_score=0.85,
        mean_cited_rerank_score=0.80,
        citation_pass_rate=1.0,
        verified_claim_count=2,
        dropped_claim_count=0,
        has_conflicting_evidence=True,
    )
    assert cat_conflict == "Conflicting"

    cat_none, score_none = compute_retrieval_confidence(
        top_rerank_score=0.0,
        mean_cited_rerank_score=0.0,
        citation_pass_rate=0.0,
        verified_claim_count=0,
        dropped_claim_count=0,
    )
    assert cat_none == "None"
    assert score_none == 0.0
