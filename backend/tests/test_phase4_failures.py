"""Phase 4 tests: failure chain reconstruction, evidence_validator, chronology vs causality."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.models.failure_kg import FailureEvent, FailureRelationship
from app.services.failures.evidence_validator import (
    validate_failure_chain_records,
    verify_quote_in_chunk,
)
from app.services.failures.reconstructor import (
    FailureChainService,
    _LLMExtractedEvent,
    _LLMExtractedRelationship,
    _LLMFailureChainOutput,
)
from app.services.llm.client import LLMClient
from app.services.retrieval.hybrid import RetrievedCandidate


class _StubFailureLLM(LLMClient):
    model_name = "stub-llm"

    def __init__(self, output: _LLMFailureChainOutput) -> None:
        self._output = output

    def generate_structured(self, system_prompt, user_prompt, schema_cls, max_retries=2):
        return self._output


def test_evidence_validator_verifies_supported_and_keeps_unsupported_pending() -> None:
    doc_id = uuid.uuid4()
    c1_id = uuid.uuid4()
    c2_id = uuid.uuid4()

    chunk_map = {
        c1_id: (
            doc_id,
            10,
            "The ground software file Small Forces supplied thruster impulse in pound-seconds instead of Newton-seconds.",
        ),
        c2_id: (
            doc_id,
            14,
            "Mars Climate Orbiter entered the atmosphere at 57 km instead of the planned 226 km altitude.",
        ),
    }

    ev1 = FailureEvent(
        id=uuid.uuid4(),
        mission="Mars Climate Orbiter",
        event_type="initial_defect",
        title="Small Forces English units defect",
        description="Thruster impulse output in pound-seconds.",
        event_order=1,
        evidence_classification="official_root_cause",
        verification_status="pending",
        document_id=doc_id,
        page_number=10,
        chunk_id=c1_id,
        evidence_text="Small Forces supplied thruster impulse in pound-seconds instead of Newton-seconds",
    )
    ev2 = FailureEvent(
        id=uuid.uuid4(),
        mission="Mars Climate Orbiter",
        event_type="mission_loss",
        title="Low atmospheric entry",
        description="Spacecraft entered Mars atmosphere at 57 km.",
        event_order=2,
        evidence_classification="explicitly_stated",
        verification_status="pending",
        document_id=doc_id,
        page_number=14,
        chunk_id=c2_id,
        evidence_text="entered the atmosphere at 57 km instead of the planned 226 km",
    )
    ev3_bad = FailureEvent(
        id=uuid.uuid4(),
        mission="Mars Climate Orbiter",
        event_type="anomaly",
        title="Fabricated battery short",
        description="Ungrounded claim.",
        event_order=3,
        evidence_classification="system_inference",
        verification_status="pending",
        document_id=doc_id,
        page_number=14,
        chunk_id=c2_id,
        evidence_text="battery electrolyte boiled in cruise",  # Not in chunk!
    )

    rel_valid = FailureRelationship(
        id=uuid.uuid4(),
        source_event_id=ev2.id,
        target_event_id=ev1.id,
        relationship_type="caused_by",
        verification_status="pending",
        document_id=doc_id,
        page_number=10,
        evidence_chunk_id=c1_id,
        evidence_text="Small Forces supplied thruster impulse in pound-seconds",
    )
    rel_unverified_endpoint = FailureRelationship(
        id=uuid.uuid4(),
        source_event_id=ev3_bad.id,
        target_event_id=ev2.id,
        relationship_type="preceded_by",
        verification_status="pending",
        document_id=doc_id,
        page_number=14,
        evidence_chunk_id=c2_id,
        evidence_text="entered the atmosphere at 57 km",
    )

    v_events, v_rels = validate_failure_chain_records(
        db=MagicMock(),
        document_id=doc_id,
        events=[ev1, ev2, ev3_bad],
        relationships=[rel_valid, rel_unverified_endpoint],
        chunk_text_map=chunk_map,
    )

    assert v_events == 2
    assert ev1.verification_status == "verified"
    assert ev2.verification_status == "verified"
    assert ev3_bad.verification_status == "pending"

    assert v_rels == 1
    assert rel_valid.verification_status == "verified"
    # Even though rel_unverified_endpoint had a valid quote, ev3_bad is unverified -> stays pending!
    assert rel_unverified_endpoint.verification_status == "pending"


def test_reconstructor_uses_shared_retriever_and_separates_chronology_from_causality() -> None:
    doc_id = uuid.uuid4()
    c1 = RetrievedCandidate(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        doc_code="NASA-A13-1970",
        document_title="Report of Apollo 13 Review Board",
        source_url="https://ntrs.nasa.gov/api/citations/19700076776/downloads/19700076776.pdf",
        licence="Public Domain",
        mission="Apollo 13",
        section_id=uuid.uuid4(),
        section_title="Chapter 4 Findings",
        section_path="4.2",
        page_number=42,
        text="Thermostatic switches in oxygen tank No. 2 were welded closed during detanking using 65 volts.",
        bbox_json=[],
        rerank_score=0.91,
    )
    c2 = RetrievedCandidate(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        doc_code="NASA-A13-1970",
        document_title="Report of Apollo 13 Review Board",
        source_url="https://ntrs.nasa.gov/api/citations/19700076776/downloads/19700076776.pdf",
        licence="Public Domain",
        mission="Apollo 13",
        section_id=uuid.uuid4(),
        section_title="Chapter 4 Findings",
        section_path="4.3",
        page_number=44,
        text="During cryo stir at 55:54 MET, damaged Teflon insulation ignited and ruptured oxygen tank No. 2.",
        bbox_json=[],
        rerank_score=0.93,
    )

    fake_retriever = MagicMock()
    fake_retriever.search.return_value = ([c1, c2], {"total_ms": 10.0})

    llm_out = _LLMFailureChainOutput(
        events=[
            _LLMExtractedEvent(
                temp_id="e1",
                event_type="initial_defect",
                title="Thermostatic switches welded closed",
                description="65V ground test damaged tank No. 2 thermostats.",
                event_order=1,
                timestamp_label="Pre-launch KSC",
                subsystem="Cryogenic Oxygen Tank No. 2",
                evidence_classification="official_contributing_factor",
                chunk_id=str(c1.chunk_id),
                evidence_quote="Thermostatic switches in oxygen tank No. 2 were welded closed during detanking",
            ),
            _LLMExtractedEvent(
                temp_id="e2",
                event_type="mission_loss",
                title="Oxygen tank No. 2 rupture",
                description="Damaged Teflon wiring ignited during cryo stir.",
                event_order=2,
                timestamp_label="55:54 MET",
                subsystem="Service Module Bay 4",
                evidence_classification="official_root_cause",
                chunk_id=str(c2.chunk_id),
                evidence_quote="damaged Teflon insulation ignited and ruptured oxygen tank No. 2",
            ),
        ],
        relationships=[
            _LLMExtractedRelationship(
                source_temp_id="e2",
                target_temp_id="e1",
                relationship_type="caused_by",
                evidence_chunk_id=str(c2.chunk_id),
                evidence_quote="damaged Teflon insulation ignited and ruptured oxygen tank No. 2",
            ),
            _LLMExtractedRelationship(
                source_temp_id="e1",
                target_temp_id="e2",
                relationship_type="preceded_by",
                evidence_chunk_id=str(c2.chunk_id),
                evidence_quote="fabricated chronology quote not in text",  # Should stay pending
            ),
        ],
    )

    doc_orm = MagicMock()
    doc_orm.id = doc_id
    doc_orm.doc_code = "NASA-A13-1970"
    doc_orm.title = "Report of Apollo 13 Review Board"
    doc_orm.mission = "Apollo 13"

    mock_db = MagicMock()
    mock_db.get.return_value = doc_orm
    mock_db.execute.return_value.all.return_value = []

    service = FailureChainService(retriever=fake_retriever, llm_client=_StubFailureLLM(llm_out))
    res = service.reconstruct_for_document(mock_db, doc_id, force_rebuild=True)

    assert len(res.events) == 2
    assert res.verified_events == 2
    assert len(res.relationships) == 2
    assert res.verified_relationships == 1
    assert res.relationships[0].relationship_type == "caused_by"
    assert res.relationships[0].verification_status == "verified"
    assert res.relationships[1].relationship_type == "preceded_by"
    assert res.relationships[1].verification_status == "pending"


def test_quote_verification_requires_real_overlap() -> None:
    chunk = "Hall effect sensors on the Mars Polar Lander landing legs generated spurious signals."
    assert verify_quote_in_chunk("landing legs generated spurious signals", chunk) is True
    assert verify_quote_in_chunk("solar panel exploded during launch", chunk) is False
