"""Tests for the pre-response Citation Validator."""

from __future__ import annotations

import uuid

from app.services.rag.citation_validator import (
    LLMCitationRef,
    LLMClaimItem,
    LLMRAGOutput,
    validate_and_filter_claims,
)
from app.services.retrieval.hybrid import RetrievedCandidate


def _sample_candidate(
    page_number: int = 24,
    text: str = (
        "The root cause of the Mars Climate Orbiter mishap was the failure to use "
        "metric units in the coding of a ground software file, Small Forces, used in "
        "trajectory models."
    ),
) -> RetrievedCandidate:
    return RetrievedCandidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_code="NASA-MCO-1999",
        document_title="Mars Climate Orbiter Mishap Investigation Board Phase I Report",
        source_url="https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf",
        licence="Public Domain (U.S. Government Work - NASA)",
        mission="Mars Climate Orbiter",
        section_id=uuid.uuid4(),
        section_title="3.2 Root Cause",
        section_path="3.2",
        page_number=page_number,
        text=text,
        bbox_json=[
            {
                "page": page_number,
                "x0": 72.0,
                "y0": 140.0,
                "x1": 520.0,
                "y1": 210.0,
                "page_width": 612.0,
                "page_height": 792.0,
            }
        ],
        dense_score=0.88,
        bm25_score=9.2,
        rrf_score=0.032,
        rerank_score=0.91,
    )


def test_valid_citation_passes_and_resolves_provenance() -> None:
    cand = _sample_candidate()
    llm_out = LLMRAGOutput(
        claims=[
            LLMClaimItem(
                claim_text="The official root cause was failing to use metric units in the Small Forces ground software file.",
                evidence_classification="official_root_cause",
                citation_refs=[
                    LLMCitationRef(
                        chunk_id=str(cand.chunk_id),
                        document_id=str(cand.document_id),
                        page_number=24,
                        quote="failure to use metric units in the coding of a ground software file, Small Forces",
                    )
                ],
            )
        ]
    )

    report = validate_and_filter_claims(llm_out, [cand], db=None)
    assert len(report.verified_claims) == 1
    assert len(report.verified_citations) == 1
    assert report.stripped_citations_count == 0
    assert report.dropped_claims_count == 0
    assert report.needs_regeneration is False
    assert report.verified_citations[0].doc_code == "NASA-MCO-1999"
    assert report.verified_citations[0].page_number == 24


def test_fabricated_chunk_id_is_stripped_and_triggers_regeneration() -> None:
    cand = _sample_candidate()
    fake_chunk_id = str(uuid.uuid4())
    llm_out = LLMRAGOutput(
        claims=[
            LLMClaimItem(
                claim_text="Thruster data used English units.",
                evidence_classification="explicitly_stated",
                citation_refs=[
                    LLMCitationRef(
                        chunk_id=fake_chunk_id,
                        page_number=24,
                        quote="failure to use metric units in the coding of a ground software file",
                    )
                ],
            )
        ]
    )

    report = validate_and_filter_claims(llm_out, [cand], db=None)
    assert len(report.verified_claims) == 0
    assert report.stripped_citations_count == 1
    assert report.dropped_claims_count == 1
    assert report.needs_regeneration is True


def test_mismatched_page_number_is_rejected() -> None:
    cand = _sample_candidate(page_number=24)
    llm_out = LLMRAGOutput(
        claims=[
            LLMClaimItem(
                claim_text="Small Forces lacked metric unit conversion.",
                evidence_classification="official_root_cause",
                citation_refs=[
                    LLMCitationRef(
                        chunk_id=str(cand.chunk_id),
                        page_number=99,  # Wrong page
                        quote="failure to use metric units in the coding of a ground software file",
                    )
                ],
            )
        ]
    )

    report = validate_and_filter_claims(llm_out, [cand], db=None)
    assert len(report.verified_claims) == 0
    assert report.stripped_citations_count == 1
    assert report.needs_regeneration is True


def test_ungrounded_quote_is_stripped_while_valid_claim_survives() -> None:
    cand = _sample_candidate(page_number=24)
    llm_out = LLMRAGOutput(
        claims=[
            LLMClaimItem(
                claim_text="Valid claim supported by chunk.",
                evidence_classification="official_root_cause",
                citation_refs=[
                    LLMCitationRef(
                        chunk_id=str(cand.chunk_id),
                        page_number=24,
                        quote="failure to use metric units in the coding of a ground software file",
                    )
                ],
            ),
            LLMClaimItem(
                claim_text="Solar panel delamination caused complete power loss during cruise.",
                evidence_classification="system_inference",
                citation_refs=[
                    LLMCitationRef(
                        chunk_id=str(cand.chunk_id),
                        page_number=24,
                        quote="solar array photovoltaic cells melted in orbit",
                    )
                ],
            ),
        ]
    )

    report = validate_and_filter_claims(llm_out, [cand], db=None)
    assert len(report.verified_claims) == 1
    assert report.verified_claims[0].claim_text == "Valid claim supported by chunk."
    assert report.stripped_citations_count == 1
    assert report.dropped_claims_count == 1
    assert report.needs_regeneration is False
