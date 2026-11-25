"""Phase 5 tests: incident extraction, similar-failures boost/breakdown, and multi-hop KG queries."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.models.failure_kg import MissionIncident
from app.services.incidents.indexer import (
    IncidentKGIndexer,
    infer_mechanism_from_text,
    infer_subsystem_from_text,
)
from app.services.incidents.similar_search import (
    SimilarFailuresService,
    compute_subsystem_boost,
    extract_problem_entities,
)
from app.services.kg.service import KnowledgeGraphService
from app.services.retrieval.hybrid import RetrievedCandidate


def test_problem_entity_extraction_and_subsystem_boost() -> None:
    profile = extract_problem_entities(
        "Ground software Small Forces thruster impulse unit mismatch in pound-seconds vs Newton-seconds"
    )
    assert "Propulsion & Thrusters" in profile.subsystems
    assert "Navigation & Flight Software" in profile.subsystems
    assert "unit_conversion_mismatch" in profile.mechanisms

    inc_match = MissionIncident(
        id=uuid.uuid4(),
        mission="Mars Climate Orbiter",
        subsystem="Propulsion & Thrusters",
        component="Small Forces",
        anomaly_title="Thruster impulse unit mismatch",
        anomaly_description="Small Forces output pound-seconds instead of Newton-seconds.",
        root_cause="Failure to convert English units to metric.",
        consequence="Loss of spacecraft.",
        corrective_action="Verify SIS unit conversion end-to-end.",
        failure_mechanism="unit_conversion_mismatch",
        document_id=uuid.uuid4(),
        page_number=6,
        chunk_id=uuid.uuid4(),
        evidence_text="Small Forces output pound-seconds.",
    )
    inc_other = MissionIncident(
        id=uuid.uuid4(),
        mission="Apollo 13",
        subsystem="Power & Cryogenic Storage",
        component="Oxygen Tank No. 2",
        anomaly_title="Tank rupture",
        anomaly_description="Thermostat switch welded closed.",
        root_cause="65V heater ground test damage.",
        consequence="Service Module power loss.",
        corrective_action="Remove Teflon and thermostatic switches inside cryo tank.",
        failure_mechanism="electrical_short_ignition",
        document_id=uuid.uuid4(),
        page_number=42,
        chunk_id=uuid.uuid4(),
        evidence_text="Thermostat switch welded closed.",
    )

    boost_match, terms_match = compute_subsystem_boost(profile, inc_match)
    boost_other, _ = compute_subsystem_boost(profile, inc_other)
    assert boost_match > boost_other
    assert boost_match >= 0.8
    assert "Propulsion & Thrusters" in terms_match


def test_similar_failures_search_ranks_and_returns_transparent_breakdown(monkeypatch) -> None:
    doc1 = MagicMock(
        id=uuid.uuid4(),
        doc_code="NASA-MCO-1999",
        title="MCO Phase I Report",
        source_url="https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf",
        licence="Public Domain",
    )
    doc2 = MagicMock(
        id=uuid.uuid4(),
        doc_code="NASA-A13-1970",
        title="Apollo 13 Review Board",
        source_url="https://ntrs.nasa.gov/api/citations/19700076776/downloads/19700076776.pdf",
        licence="Public Domain",
    )
    chunk_mock = MagicMock(bbox_json=[{"page": 6, "x0": 10, "y0": 20, "x1": 100, "y1": 50, "page_width": 612, "page_height": 792}])
    sec_mock = MagicMock(title="Root Cause")

    inc1 = MissionIncident(
        id=uuid.uuid4(),
        mission="Mars Climate Orbiter",
        subsystem="Propulsion & Thrusters",
        component="Small Forces",
        anomaly_title="Propulsion thruster impulse unit mismatch",
        anomaly_description="Ground software Small Forces output pound-seconds instead of Newton-seconds.",
        root_cause="Missing metric conversion.",
        consequence="Spacecraft lost at Mars.",
        corrective_action="Audit SIS and verify thruster impulse units.",
        failure_mechanism="unit_conversion_mismatch",
        evidence_classification="official_root_cause",
        verification_status="verified",
        document_id=doc1.id,
        page_number=6,
        chunk_id=uuid.uuid4(),
        evidence_text="Small Forces output pound-seconds.",
        embedding=[1.0, 0.0],
    )
    inc2 = MissionIncident(
        id=uuid.uuid4(),
        mission="Apollo 13",
        subsystem="Power & Cryogenic Storage",
        component="Oxygen Tank No. 2",
        anomaly_title="Cryogenic tank heater short",
        anomaly_description="Oxygen tank No. 2 ruptured during cryo stir.",
        root_cause="Heater thermostat welded closed.",
        consequence="Aborted lunar landing.",
        corrective_action="Redesign tank heater wiring.",
        failure_mechanism="electrical_short_ignition",
        evidence_classification="official_root_cause",
        verification_status="verified",
        document_id=doc2.id,
        page_number=44,
        chunk_id=uuid.uuid4(),
        evidence_text="Oxygen tank No. 2 ruptured.",
        embedding=[0.2, 0.9],
    )

    fake_embedder = MagicMock()
    fake_embedder.embed_query.return_value = [0.98, 0.05]
    fake_reranker = MagicMock()
    fake_reranker.score_pairs.return_value = [0.92, 0.14]

    monkeypatch.setattr("app.services.incidents.similar_search.get_embedding_service", lambda: fake_embedder)
    monkeypatch.setattr("app.services.incidents.similar_search.get_reranker", lambda: fake_reranker)

    mock_db = MagicMock()
    mock_db.execute.return_value.all.return_value = [
        (inc1, doc1, chunk_mock, sec_mock),
        (inc2, doc2, chunk_mock, sec_mock),
    ]

    profile, matches = SimilarFailuresService().search(
        mock_db,
        problem_description="propulsion thruster impulse unit mismatch in pound-seconds",
        top_k=5,
    )
    assert "Propulsion & Thrusters" in profile.subsystems
    assert len(matches) == 2
    assert matches[0].incident.mission == "Mars Climate Orbiter"
    assert matches[0].subsystem_match_score > matches[1].subsystem_match_score
    assert matches[0].total_relevance > matches[1].total_relevance


def test_multihop_kg_query_returns_cited_propulsion_actions() -> None:
    doc = MagicMock(
        id=uuid.uuid4(),
        doc_code="NASA-MCO-1999",
        title="MCO Phase I Report",
        source_url="https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf",
        licence="Public Domain",
    )
    chunk = MagicMock(bbox_json=[])
    sec = MagicMock(title="Recommendations")

    inc_prop = MissionIncident(
        id=uuid.uuid4(),
        mission="Mars Climate Orbiter",
        subsystem="Propulsion & Thrusters",
        component="Small Forces",
        anomaly_title="Thruster impulse unit mismatch",
        anomaly_description="AMD thruster data was supplied in pound-seconds.",
        root_cause="Missing metric conversion.",
        consequence="Loss of mission.",
        corrective_action="Verify Software Interface Specifications and propulsion impulse units.",
        failure_mechanism="unit_conversion_mismatch",
        verification_status="verified",
        document_id=doc.id,
        page_number=24,
        chunk_id=uuid.uuid4(),
        evidence_text="Verify Software Interface Specifications.",
    )
    inc_power = MissionIncident(
        id=uuid.uuid4(),
        mission="Apollo 13",
        subsystem="Power & Cryogenic Storage",
        component="Oxygen Tank No. 2",
        anomaly_title="Oxygen tank rupture",
        anomaly_description="Tank No. 2 wiring short.",
        root_cause="Thermostat welded closed.",
        consequence="Service module damage.",
        corrective_action="Redesign tank heater wiring.",
        failure_mechanism="electrical_short_ignition",
        verification_status="verified",
        document_id=doc.id,
        page_number=44,
        chunk_id=uuid.uuid4(),
        evidence_text="Redesign tank heater wiring.",
    )

    mock_db = MagicMock()
    mock_db.execute.return_value.all.return_value = [
        (inc_prop, doc, chunk, sec),
        (inc_power, doc, chunk, sec),
    ]

    res = KnowledgeGraphService().query_multihop(
        mock_db, "missions with propulsion anomalies and their corrective actions"
    )
    assert res["abstained"] is False
    assert len(res["paths"]) == 1
    assert res["paths"][0]["mission"] == "Mars Climate Orbiter"
    assert "Software Interface Specifications" in res["paths"][0]["corrective_action"]
    assert res["citations"][0]["page_number"] == 24


def test_indexer_extractive_fallback_creates_verified_incidents_and_kg_relations(monkeypatch) -> None:
    doc_id = uuid.uuid4()
    doc = MagicMock(
        id=doc_id,
        doc_code="NASA-MPL-2000",
        title="Mars Polar Lander Report",
        mission="Mars Polar Lander",
    )
    cand = RetrievedCandidate(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        doc_code="NASA-MPL-2000",
        document_title="Mars Polar Lander Report",
        source_url="https://ntrs.nasa.gov/api/citations/20000061966/downloads/20000061966.pdf",
        licence="Public Domain",
        mission="Mars Polar Lander",
        section_id=uuid.uuid4(),
        section_title="Findings",
        section_path="2.1",
        page_number=35,
        text=(
            "The most probable cause of the Mars Polar Lander loss was premature shutdown of the "
            "descent engines due to spurious signals from the landing leg Hall effect sensors. "
            "The board recommends end-to-end system-level testing of flight software."
        ),
        bbox_json=[],
        rerank_score=0.9,
    )
    fake_retriever = MagicMock()
    fake_retriever.search.return_value = ([cand], {})
    fake_embedder = MagicMock()
    fake_embedder.embed_passages.return_value = [[0.1] * 384]

    monkeypatch.setattr("app.services.incidents.indexer.get_embedding_service", lambda: fake_embedder)

    mock_db = MagicMock()
    mock_db.get.return_value = doc

    res = IncidentKGIndexer(retriever=fake_retriever).index_document(mock_db, doc_id, force_rebuild=True)
    assert res.incidents_indexed == 1
    assert res.verified_incidents == 1
    assert res.entities_created >= 4
    assert res.relations_created >= 4
    assert infer_subsystem_from_text(cand.text) in ("Landing & Touchdown Systems", "Propulsion & Thrusters")
    assert infer_mechanism_from_text(cand.text) == "spurious_sensor_transient"
