"""Comprehensive tests for P0 deliverables: Multi-format parsing, upload hardening, job queue, and classification scoping."""

from __future__ import annotations

import io
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.errors import ApiError
from app.core.security import (
    validate_provenance_fields,
    validate_upload_bytes,
)
from app.models.documents import Document, DocumentChunk, DocumentEmbedding, DocumentSection, IngestionJob
from app.services.ingestion.format_parsers import (
    UniversalDocumentParser,
    parse_csv,
    parse_docx,
    parse_html,
    parse_markdown,
    parse_pptx,
    parse_text,
    parse_xlsx,
    parse_xml,
)
from app.services.ingestion.job_queue import IngestionJobManager
from app.services.retrieval.hybrid import HybridRetriever
from app.services.retrieval.section_selector import L1PassThroughSectionSelector


@pytest.fixture
def in_memory_db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Document.__table__.create(engine)
    IngestionJob.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_parse_text():
    sample_text = (
        "1.0 INTRODUCTION\n"
        "This is the introductory section of the test report.\n\n"
        "2.0 PROPULSION ANOMALY\n"
        "The small forces thruster data had an unexpected unit conversion error.\n"
    )
    doc = parse_text(sample_text.encode("utf-8"), "report.txt")
    assert doc.page_count >= 1
    assert len(doc.sections) >= 2
    assert any("PROPULSION ANOMALY" in s.title for s in doc.sections)
    assert len(doc.pages[0].blocks) >= 2


def test_parse_markdown():
    sample_md = (
        "# Executive Summary\n\n"
        "The Mars Climate Orbiter failed due to unit discrepancy.\n\n"
        "## Subsystem Findings\n\n"
        "| Subsystem | Status | Discrepancy |\n"
        "| --- | --- | --- |\n"
        "| Navigation | Failed | English vs Metric |\n"
        "| Propulsion | Operating | None |\n"
    )
    doc = parse_markdown(sample_md.encode("utf-8"), "mco_summary.md")
    assert doc.page_count >= 1
    assert any(s.title == "Executive Summary" for s in doc.sections)
    assert any(s.title == "Subsystem Findings" for s in doc.sections)
    # Check that table was parsed
    assert any("Navigation" in b.text and "Metric" in b.text for b in doc.pages[0].blocks)


def test_parse_html():
    sample_html = (
        "<!DOCTYPE html><html><head><title>Apollo 13 Review</title></head>"
        "<body>"
        "<h1>Cryogenic Storage Failure</h1>"
        "<p>Oxygen Tank No. 2 experienced an electrical short in its internal wiring.</p>"
        "<table><tr><th>Tank</th><th>Pressure</th></tr><tr><td>Tank 2</td><td>0 psia</td></tr></table>"
        "</body></html>"
    )
    doc = parse_html(sample_html.encode("utf-8"), "a13.html")
    assert doc.page_count >= 1
    assert any("Cryogenic Storage" in s.title for s in doc.sections)
    assert any("Tank 2" in b.text for b in doc.pages[0].blocks)


def test_parse_csv():
    sample_csv = "Mission,Subsystem,Anomaly\nMCO,Navigation,Pound-seconds\nA13,Cryogenic,Oxygen Tank\n"
    doc = parse_csv(sample_csv.encode("utf-8"), "incidents.csv")
    assert doc.page_count >= 1
    assert len(doc.pages[0].blocks) >= 1
    assert "Pound-seconds" in doc.pages[0].blocks[0].text


def test_parse_xml_and_entity_defense():
    sample_xml = (
        "<mission_report>"
        "<mission>Mars Polar Lander</mission>"
        "<finding>Premature engine shutdown triggered by spurious Hall effect touchdown sensor.</finding>"
        "</mission_report>"
    )
    doc = parse_xml(sample_xml.encode("utf-8"), "mpl.xml")
    assert doc.page_count >= 1
    assert any("finding" in s.title for s in doc.sections)

    # Malicious XXE attack payload
    xxe_payload = b'<!DOCTYPE test [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]><test>&xxe;</test>'
    with pytest.raises(ApiError) as exc_info:
        parse_xml(xxe_payload, "exploit.xml")
    assert exc_info.value.code == "XML_ENTITY_INJECTION_BLOCKED"


def test_parse_docx():
    import docx

    doc_obj = docx.Document()
    doc_obj.add_heading("Mission Overview", level=1)
    doc_obj.add_paragraph("The spacecraft entered the Martian atmosphere below safe entry corridors.")
    tbl = doc_obj.add_table(rows=2, cols=2)
    tbl.cell(0, 0).text = "Param"
    tbl.cell(0, 1).text = "Value"
    tbl.cell(1, 0).text = "Periapsis"
    tbl.cell(1, 1).text = "57 km"

    buf = io.BytesIO()
    doc_obj.save(buf)
    docx_bytes = buf.getvalue()

    doc = parse_docx(docx_bytes, "mission_report.docx")
    assert doc.page_count >= 1
    assert any("Mission Overview" in s.title for s in doc.sections)
    assert any("57 km" in b.text for b in doc.pages[0].blocks)


def test_parse_pptx():
    import pptx

    prs = pptx.Presentation()
    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)
    title = slide.shapes.title
    title.text = "Flight Readiness Review"
    subtitle = slide.placeholders[1]
    subtitle.text = "Thermal and propulsion status for Mars insertion."

    buf = io.BytesIO()
    prs.save(buf)
    pptx_bytes = buf.getvalue()

    doc = parse_pptx(pptx_bytes, "frr_slides.pptx")
    assert doc.page_count == 1
    assert any("Flight Readiness Review" in s.title for s in doc.sections)
    assert any("thermal and propulsion" in b.text.lower() for b in doc.pages[0].blocks)


def test_validate_upload_bytes_and_zip_bomb():
    # Valid text
    sha = validate_upload_bytes(b"Clean plain text contents", "notes.txt")
    assert len(sha) == 64

    # Unsupported extension
    with pytest.raises(ApiError) as exc:
        validate_upload_bytes(b"binary", "payload.exe")
    assert exc.value.code == "INVALID_EXTENSION"

    # Zip bomb attack simulation (high uncompressed ratio)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("huge.txt", b"A" * (250 * 1024 * 1024))  # 250 MB uncompressed
    zip_bomb_bytes = buf.getvalue()

    with pytest.raises(ApiError) as exc_info:
        validate_upload_bytes(zip_bomb_bytes, "danger.docx", max_upload_mb=50)
    assert exc_info.value.code == "ZIP_BOMB_DETECTED"


def test_provenance_allows_uploaded_no_public_url():
    url, licence = validate_provenance_fields("uploaded, no public URL", "Proprietary Test")
    assert url == "uploaded, no public URL"
    assert licence == "Proprietary Test"

    url2, licence2 = validate_provenance_fields("", "NASA Public", allow_empty_url_as_uploaded=True)
    assert url2 == "uploaded, no public URL"
    assert licence2 == "NASA Public"


def test_ingestion_job_manager_lifecycle(in_memory_db: Session):
    manager = IngestionJobManager()
    job = manager.create_job(
        db=in_memory_db,
        filename="telemetry.txt",
        doc_code="TEST-TEL-01",
        title="Telemetry Log",
        source_url="uploaded, no public URL",
        licence="Public Domain",
        raw_bytes=b"Sample telemetry log data\nHeading 1\nVal: 42\n",
    )
    assert job.status == "queued"
    assert job.job_id.startswith("job_")

    fetched = manager.get_job(in_memory_db, job.job_id)
    assert fetched is not None
    assert fetched.doc_code == "TEST-TEL-01"

    # Test cancel
    cancelled = manager.cancel_job(in_memory_db, job.job_id)
    assert cancelled is True
    assert manager.get_job(in_memory_db, job.job_id).status == "cancelled"


def test_document_classification_scoping(in_memory_db: Session):
    # Create public, internal, and restricted documents
    doc_pub = Document(
        id=uuid.uuid4(),
        doc_code="PUB-01",
        title="Public Report",
        source_url="uploaded, no public URL",
        licence="Public",
        org="NASA",
        mission="Test",
        file_path="/storage/pub.pdf",
        file_hash="hash_pub_123",
        classification="public",
        page_count=1,
    )
    doc_res = Document(
        id=uuid.uuid4(),
        doc_code="RES-01",
        title="Restricted Classified Report",
        source_url="uploaded, no public URL",
        licence="Restricted",
        org="NASA",
        mission="Test",
        file_path="/storage/res.pdf",
        file_hash="hash_res_123",
        classification="restricted",
        page_count=1,
    )
    in_memory_db.add_all([doc_pub, doc_res])
    in_memory_db.commit()

    # Query with public clearance only
    from sqlalchemy import select
    allowed_viewer = ["public"]
    docs_viewer = in_memory_db.execute(
        select(Document).where(Document.classification.in_(allowed_viewer))
    ).scalars().all()
    assert len(docs_viewer) == 1
    assert docs_viewer[0].doc_code == "PUB-01"

    # Query with admin clearance
    allowed_admin = ["public", "internal", "restricted"]
    docs_admin = in_memory_db.execute(
        select(Document).where(Document.classification.in_(allowed_admin))
    ).scalars().all()
    assert len(docs_admin) == 2
