"""Phase 3 tests: typed-vs-spoken citation parity, follow-up query rewriter, spoken formatter, WS barge-in."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.config import ABSTENTION_MESSAGE
from app.main import app
from app.schemas import CitationOut, ClaimOut
from app.services.llm.client import LLMClient
from app.services.rag.citation_validator import LLMCitationRef, LLMClaimItem, LLMRAGOutput
from app.services.rag.query_rewriter import rewrite_followup_query
from app.services.rag.service import RAGService
from app.services.rag.spoken_formatter import format_spoken_answer
from app.services.retrieval.hybrid import RetrievedCandidate
from app.services.voice.aerospace_vocab import build_aerospace_vocab_prompt
from app.services.voice.stt import TranscriptionResult


class _FixedRAGLLM(LLMClient):
    model_name = "stub-llm"

    def __init__(self, chunk_id: uuid.UUID, doc_id: uuid.UUID) -> None:
        self._chunk_id = chunk_id
        self._doc_id = doc_id

    def generate_structured(self, system_prompt, user_prompt, schema_cls, max_retries=2):
        return LLMRAGOutput(
            claims=[
                LLMClaimItem(
                    claim_text=(
                        "The Mars Climate Orbiter root cause was failing to convert thruster "
                        "impulse data from English pound-seconds to metric Newton-seconds in the Small Forces file."
                    ),
                    evidence_classification="official_root_cause",
                    citation_refs=[
                        LLMCitationRef(
                            chunk_id=str(self._chunk_id),
                            document_id=str(self._doc_id),
                            page_number=6,
                            quote="failure to use metric units in the coding of a ground software file, Small Forces",
                        )
                    ],
                ),
                LLMClaimItem(
                    claim_text="Trajectory models under-predicted momentum desaturation perturbations during cruise.",
                    evidence_classification="official_contributing_factor",
                    citation_refs=[
                        LLMCitationRef(
                            chunk_id=str(self._chunk_id),
                            document_id=str(self._doc_id),
                            page_number=6,
                            quote="Small Forces, used in trajectory models",
                        )
                    ],
                ),
            ]
        )


def _sample_candidate() -> RetrievedCandidate:
    return RetrievedCandidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_code="NASA-MCO-1999",
        document_title="Mars Climate Orbiter Mishap Investigation Board Phase I Report",
        source_url="https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf",
        licence="Public Domain (U.S. Government Work - NASA)",
        mission="Mars Climate Orbiter",
        section_id=uuid.uuid4(),
        section_title="Root Cause",
        section_path="3.2",
        page_number=6,
        text=(
            "The root cause was the failure to use metric units in the coding of a ground "
            "software file, Small Forces, used in trajectory models. Thruster impulse data "
            "was supplied in English units (pound-seconds) instead of Newton-seconds."
        ),
        bbox_json=[
            {"page": 6, "x0": 72, "y0": 150, "x1": 500, "y1": 220, "page_width": 612, "page_height": 792}
        ],
        dense_score=0.90,
        bm25_score=10.1,
        rrf_score=0.032,
        rerank_score=0.94,
    )


def test_query_rewriter_resolves_followups_and_simpler_style() -> None:
    history = [
        ("user", "What caused the Apollo 13 oxygen tank No. 2 failure?"),
        ("assistant", "Thermostatic switches were damaged during detanking at 65 volts."),
    ]

    r1 = rewrite_followup_query("what was the initial issue?", history)
    assert r1.was_rewritten is True
    assert "Apollo 13" in r1.standalone_query
    assert r1.response_style == "standard"

    r2 = rewrite_followup_query("explain simpler", history)
    assert r2.was_rewritten is True
    assert r2.response_style == "simpler"
    assert "Apollo 13" in r2.standalone_query


def test_spoken_formatter_is_shorter_with_identical_claims_and_abstention() -> None:
    cit = CitationOut(
        document_id=uuid.uuid4(),
        doc_code="NASA-MCO-1999",
        document_title="MCO Report",
        source_url="https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf",
        licence="Public Domain",
        section="Root Cause",
        page_number=6,
        chunk_id=uuid.uuid4(),
        quote="failure to use metric units",
    )
    claims = [
        ClaimOut(
            claim_text="The Mars Climate Orbiter root cause was failing to use metric units in the Small Forces file. [NASA-MCO-1999 · p.6 · Root Cause]",
            evidence_classification="official_root_cause",
            citations=[cit],
        ),
        ClaimOut(
            claim_text="AMD events caused cumulative navigation errors during Mars cruise. [NASA-MCO-1999 · p.6 · Root Cause]",
            evidence_classification="official_contributing_factor",
            citations=[cit],
        ),
    ]
    written = "\n\n".join(c.claim_text for c in claims)
    spoken = format_spoken_answer(claims, abstained=False, written_answer=written, style="simpler")
    assert len(spoken) < len(written)
    assert "[" not in spoken
    assert "Angular Momentum Desaturation" in spoken

    abstained_spoken = format_spoken_answer([], abstained=True, written_answer=ABSTENTION_MESSAGE)
    assert abstained_spoken == ABSTENTION_MESSAGE


def test_typed_vs_spoken_produces_identical_citations(monkeypatch) -> None:
    """Required Phase 3 test: same question typed vs spoken produces exact same citations."""
    cand = _sample_candidate()

    fake_retriever = MagicMock()
    fake_retriever.search.return_value = (
        [cand],
        {
            "stair_level": "L1-BM25",
            "selector_name": "bm25_toc",
            "selected_sections": [],
            "top_rerank_score": 0.94,
            "top_rrf_score": 0.032,
            "total_ms": 14.0,
        },
    )

    monkeypatch.setattr(
        "app.services.rag.service.record_retrieval_log",
        lambda **kwargs: MagicMock(id=uuid.uuid4()),
    )

    # Stub DB session for persistence and chunk validation
    mock_db = MagicMock()
    mock_db.get.return_value = None
    mock_db.execute.return_value.scalars.return_value.all.return_value = []

    chunk_orm = MagicMock()
    chunk_orm.id = cand.chunk_id
    chunk_orm.section_id = cand.section_id
    chunk_orm.page_number = cand.page_number
    chunk_orm.text = cand.text
    chunk_orm.bbox_json = cand.bbox_json

    doc_orm = MagicMock()
    doc_orm.id = cand.document_id
    doc_orm.doc_code = cand.doc_code
    doc_orm.title = cand.document_title
    doc_orm.source_url = cand.source_url
    doc_orm.licence = cand.licence
    doc_orm.mission = cand.mission

    sec_orm = MagicMock()
    sec_orm.id = cand.section_id
    sec_orm.title = cand.section_title
    sec_orm.section_path = cand.section_path

    mock_db.execute.return_value.first.return_value = (chunk_orm, doc_orm, sec_orm)

    llm = _FixedRAGLLM(cand.chunk_id, cand.document_id)
    shared_rag = RAGService(retriever=fake_retriever, llm_client=llm)

    question = "What caused the Mars Climate Orbiter loss?"

    # 1. Typed chat path
    typed_res = shared_rag.chat_and_persist(
        db=mock_db,
        query=question,
        request_id="typed-1",
    )

    # 2. Spoken WS /api/voice/stream path using faster-whisper STT stub with aerospace prompt
    seen_prompts: list[str] = []

    class _StubSTT:
        def is_available(self) -> bool:
            return True

        def transcribe_bytes(self, audio_bytes: bytes, initial_prompt: str, suffix: str = ".webm"):
            seen_prompts.append(initial_prompt)
            return TranscriptionResult(text=question, language="en", duration_s=1.8)

    class _StubTTS:
        def is_available(self) -> bool:
            return False

        def synthesize(self, text: str):
            from app.services.voice.tts import SynthesisResult

            return SynthesisResult(audio_bytes=None, mime_type="application/json", used_fallback=True, text=text)

    class _DummySession:
        def close(self):
            pass

        def execute(self, *args, **kwargs):
            return mock_db.execute(*args, **kwargs)

        def get(self, *args, **kwargs):
            return mock_db.get(*args, **kwargs)

        def add(self, obj):
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

        def flush(self):
            pass

        def commit(self):
            pass

    monkeypatch.setattr("app.api.voice.get_stt_service", lambda: _StubSTT())
    monkeypatch.setattr("app.api.voice.get_tts_service", lambda: _StubTTS())
    monkeypatch.setattr("app.api.voice.get_rag_service", lambda: shared_rag)
    monkeypatch.setattr("app.api.voice.SessionLocal", lambda: _DummySession())

    client = TestClient(app)
    with client.websocket_connect("/api/voice/stream") as ws:
        ws.send_bytes(b"RIFFfakewebmbytes")
        ws.send_json({"type": "end_of_speech", "suffix": ".webm"})

        transcript_msg = ws.receive_json()
        assert transcript_msg["type"] == "transcript"
        assert transcript_msg["text"] == question

        answer_msg = ws.receive_json()
        assert answer_msg["type"] == "answer"

        tts_msg = ws.receive_json()
        assert tts_msg["type"] == "tts_fallback"

        # Verify interrupt / barge-in works cleanly
        ws.send_json({"type": "interrupt"})
        int_msg = ws.receive_json()
        assert int_msg["type"] == "interrupted"

    # Assert aerospace vocabulary prompt was passed to faster-whisper
    assert len(seen_prompts) == 1
    assert "Mars Climate Orbiter" in seen_prompts[0]
    assert "Small Forces" in seen_prompts[0]

    # Assert typed vs spoken produce IDENTICAL citations and claims
    spoken_cits = answer_msg["citations"]
    assert len(spoken_cits) == len(typed_res.citations)
    assert [(c["chunk_id"], c["page_number"], c["document_id"]) for c in spoken_cits] == [
        (str(c.chunk_id), c.page_number, str(c.document_id)) for c in typed_res.citations
    ]
    assert [c["claim_text"] for c in answer_msg["claims"]] == [c.claim_text for c in typed_res.claims]
    assert len(answer_msg["spoken_text"]) < len(typed_res.answer)


def test_aerospace_vocab_prompt_contains_core_terms() -> None:
    prompt = build_aerospace_vocab_prompt(db=None)
    assert "Apollo 13" in prompt
    assert "Newton-seconds" in prompt
    assert "Mars Polar Lander" in prompt
