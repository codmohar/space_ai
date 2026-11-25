"""Phase 2 tests: 3-tier ToC extraction, SectionSelector implementations, evaluation metrics."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from app.api.eval import load_eval_results
from app.services.ingestion.pdf_extractor import (
    ExtractedBlock,
    ExtractedPage,
    _build_sections_from_heuristics,
    _repair_sections_with_llm,
)
from app.services.llm.client import LLMClient
from app.services.retrieval.section_selector import (
    BM25ToCSectionSelector,
    FineTunedSTAIRSectionSelector,
    STAIRInspiredSectionSelector,
    _STAIRSelectionOutput,
    _STAIRSectionPick,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate_retrieval import compute_query_metrics  # noqa: E402


class _StubLLM(LLMClient):
    model_name = "stub-llm"

    def __init__(self, payload) -> None:
        self._payload = payload

    def generate_structured(self, system_prompt, user_prompt, schema_cls, max_retries=2):
        return self._payload


def _fake_doc_and_sections():
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.doc_code = "NASA-MCO-1999"
    doc.title = "Mars Climate Orbiter Phase I Report"
    doc.mission = "Mars Climate Orbiter"

    sec_root = MagicMock()
    sec_root.id = uuid.uuid4()
    sec_root.document_id = doc.id
    sec_root.parent_id = None
    sec_root.title = "3. Investigation Findings"
    sec_root.level = 1
    sec_root.is_leaf = False
    sec_root.section_path = "3"
    sec_root.page_start = 10
    sec_root.page_end = 30
    sec_root.order_index = 0

    sec_leaf_1 = MagicMock()
    sec_leaf_1.id = uuid.uuid4()
    sec_leaf_1.document_id = doc.id
    sec_leaf_1.parent_id = sec_root.id
    sec_leaf_1.title = "3.2 Small Forces Unit Conversion Root Cause"
    sec_leaf_1.level = 2
    sec_leaf_1.is_leaf = True
    sec_leaf_1.section_path = "3.2"
    sec_leaf_1.page_start = 15
    sec_leaf_1.page_end = 22
    sec_leaf_1.order_index = 1

    sec_leaf_2 = MagicMock()
    sec_leaf_2.id = uuid.uuid4()
    sec_leaf_2.document_id = doc.id
    sec_leaf_2.parent_id = sec_root.id
    sec_leaf_2.title = "3.3 Solar Array Asymmetry and Momentum Desaturation"
    sec_leaf_2.level = 2
    sec_leaf_2.is_leaf = True
    sec_leaf_2.section_path = "3.3"
    sec_leaf_2.page_start = 23
    sec_leaf_2.page_end = 30
    sec_leaf_2.order_index = 2

    return doc, [sec_root, sec_leaf_1, sec_leaf_2]


def test_heuristics_extract_multilevel_numbered_toc_with_leaf_flags() -> None:
    pages = [
        ExtractedPage(
            page_number=1,
            width=612,
            height=792,
            ocr_used=False,
            ocr_confidence=None,
            ocr_low_quality=False,
            blocks=[
                ExtractedBlock(1, "1. Executive Summary", 72, 100, 300, 120, 612, 792, 14.0, True),
                ExtractedBlock(1, "1.1 Mission Overview", 72, 140, 300, 155, 612, 792, 12.0, True),
                ExtractedBlock(1, "Body paragraph explaining timeline.", 72, 170, 500, 210, 612, 792, 10.0, False),
            ],
        ),
        ExtractedPage(
            page_number=2,
            width=612,
            height=792,
            ocr_used=False,
            ocr_confidence=None,
            ocr_low_quality=False,
            blocks=[
                ExtractedBlock(2, "1.2 Root Cause Summary", 72, 100, 300, 115, 612, 792, 12.0, True),
            ],
        ),
    ]
    sections = _build_sections_from_heuristics(pages)
    assert len(sections) == 3
    assert sections[0].is_leaf is False
    assert sections[1].is_leaf is True
    assert sections[2].is_leaf is True
    assert sections[1].parent_temp_id == sections[0].temp_id
    assert all(s.extraction_method == "font_heuristic" for s in sections)


def test_llm_toc_repair_clamps_pages_and_builds_hierarchy() -> None:
    from app.services.ingestion.pdf_extractor import _LLMRepairedSectionItem, _LLMToCRepairOutput

    pages = [
        ExtractedPage(
            page_number=1,
            width=612,
            height=792,
            ocr_used=False,
            ocr_confidence=None,
            ocr_low_quality=False,
            blocks=[ExtractedBlock(1, "Contents\n1. Intro ... 1\n1.1 Details ... 3", 72, 80, 400, 150, 612, 792)],
        )
    ]
    stub = _StubLLM(
        _LLMToCRepairOutput(
            sections=[
                _LLMRepairedSectionItem(title="1. Introduction", level=1, page_start=1),
                _LLMRepairedSectionItem(title="1.1 Failure Details", level=2, page_start=999),
            ]
        )
    )
    repaired = _repair_sections_with_llm(pages, page_count=10, llm_client=stub)
    assert repaired is not None
    assert len(repaired) == 2
    assert repaired[0].is_leaf is False
    assert repaired[1].is_leaf is True
    assert repaired[1].page_start == 10  # Clamped to page_count
    assert repaired[0].extraction_method == "llm_repair"


def test_bm25_toc_selector_selects_matching_leaf_section() -> None:
    doc, sections = _fake_doc_and_sections()
    mock_db = MagicMock()
    # First execute() -> _load_toc_rows, second execute() -> lead_rows
    mock_db.execute.return_value.all.side_effect = [
        [(s, doc) for s in sections],
        [(sections[1].id, "Ground software Small Forces used pound-seconds instead of Newton-seconds.")],
    ]

    selector = BM25ToCSectionSelector()
    res = selector.select(mock_db, query="Small Forces unit conversion root cause", top_k_sections=2)
    assert res.stair_level == "L1-BM25"
    assert res.selected_section_ids is not None
    assert sections[1].id in res.selected_section_ids
    assert sections[0].id not in res.selected_section_ids  # Non-leaf excluded


def test_stair_l2_selector_validates_leaf_ids_and_counts_invalid_ids() -> None:
    doc, sections = _fake_doc_and_sections()
    mock_db = MagicMock()
    mock_db.execute.return_value.all.return_value = [(s, doc) for s in sections]

    fake_uuid = str(uuid.uuid4())
    stub_llm = _StubLLM(
        _STAIRSelectionOutput(
            selected_sections=[
                _STAIRSectionPick(section_id=str(sections[0].id), reason="Non-leaf node should be rejected"),
                _STAIRSectionPick(section_id=fake_uuid, reason="Hallucinated UUID should be rejected"),
                _STAIRSectionPick(section_id="not-a-uuid", reason="Malformed ID"),
                _STAIRSectionPick(section_id=str(sections[1].id), reason="Valid leaf section"),
            ]
        )
    )

    selector = STAIRInspiredSectionSelector(llm_client=stub_llm)
    res = selector.select(mock_db, query="Why did Small Forces cause MCO trajectory error?")
    assert res.stair_level == "L2"
    assert res.total_proposed_ids == 4
    assert res.invalid_ids_count == 3
    assert res.selected_section_ids == [sections[1].id]
    assert res.used_fallback is False


def test_stair_l3_stub_is_non_blocking_when_untrained() -> None:
    doc, sections = _fake_doc_and_sections()
    mock_db = MagicMock()
    mock_db.execute.return_value.all.side_effect = [
        [(s, doc) for s in sections],
        [(sections[2].id, "Asymmetric solar array momentum desaturation events.")],
    ]

    selector = FineTunedSTAIRSectionSelector(adapter_path="/nonexistent/stair_lora")
    assert selector.is_trained_model_available() is False
    res = selector.select(mock_db, query="solar array momentum desaturation")
    assert res.stub_not_trained is True
    assert res.used_fallback is True
    assert res.selected_section_ids is not None


def test_eval_metrics_and_unmeasured_results_contract(tmp_path: Path) -> None:
    metrics = compute_query_metrics([False, True, False, False, True])
    assert metrics["recall_at_1"] == 0.0
    assert metrics["recall_at_3"] == 1.0
    assert metrics["recall_at_5"] == 1.0
    assert metrics["mrr"] == 0.5
    assert 0.0 < metrics["ndcg_at_5"] <= 1.0

    missing_res = load_eval_results(tmp_path / "missing.json")
    assert missing_res.status == "Not yet evaluated"
    assert missing_res.methods == []

    # Verify questions.jsonl has 40+ questions and 8+ unanswerable
    q_path = REPO_ROOT / "data" / "evaluation" / "questions.jsonl"
    questions = [json.loads(line) for line in q_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(questions) >= 40
    assert sum(1 for q in questions if not q["answerable"]) >= 8
