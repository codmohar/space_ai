"""Multi-hop Engineering Knowledge Graph traversal & cited query answering."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ABSTENTION_MESSAGE
from app.models.documents import Document, DocumentChunk, DocumentSection
from app.models.failure_kg import (
    MissionEntity,
    MissionEntityRelation,
    MissionIncident,
)
from app.schemas import CitationOut
from app.services.incidents.similar_search import extract_problem_entities


@dataclass
class KGPathResult:
    mission: str
    subsystem: str
    component: Optional[str]
    anomaly: str
    root_cause: str
    corrective_action: str
    verification_status: str
    citation: CitationOut


class KnowledgeGraphService:
    def get_graph(
        self,
        db: Session,
        mission: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 200,
    ) -> tuple[list[dict], list[dict]]:
        ent_stmt = (
            select(MissionEntity, Document, DocumentChunk, DocumentSection)
            .join(Document, Document.id == MissionEntity.document_id)
            .join(DocumentChunk, DocumentChunk.id == MissionEntity.chunk_id)
            .outerjoin(DocumentSection, DocumentSection.id == MissionEntity.section_id)
            .order_by(MissionEntity.created_at.asc())
            .limit(limit)
        )
        if entity_type:
            ent_stmt = ent_stmt.where(MissionEntity.entity_type == entity_type)

        ent_rows = db.execute(ent_stmt).all()
        if mission:
            ent_rows = [
                r
                for r in ent_rows
                if (r[0].attributes or {}).get("mission", "").lower() == mission.strip().lower()
                or r[1].mission.lower() == mission.strip().lower()
            ]

        entity_ids = {r[0].id for r in ent_rows}
        nodes = [
            {
                "id": str(ent.id),
                "entity_type": ent.entity_type,
                "name": ent.name,
                "mission": (ent.attributes or {}).get("mission") or doc.mission,
                "document_id": str(doc.id),
                "doc_code": doc.doc_code,
                "document_title": doc.title,
                "source_url": doc.source_url,
                "licence": doc.licence,
                "section": sec.title if sec else "Document Body",
                "page_number": ent.page_number,
                "chunk_id": str(ent.chunk_id),
                "evidence_text": ent.evidence_text,
                "bbox_json": list(chunk.bbox_json or []),
            }
            for ent, doc, chunk, sec in ent_rows
        ]

        edges: list[dict] = []
        if entity_ids:
            rel_rows = (
                db.execute(
                    select(MissionEntityRelation).where(
                        MissionEntityRelation.source_entity_id.in_(list(entity_ids)),
                        MissionEntityRelation.target_entity_id.in_(list(entity_ids)),
                    )
                )
                .scalars()
                .all()
            )
            edges = [
                {
                    "id": str(r.id),
                    "source_entity_id": str(r.source_entity_id),
                    "target_entity_id": str(r.target_entity_id),
                    "relation_type": r.relation_type,
                    "verification_status": r.verification_status,
                    "page_number": r.page_number,
                    "evidence_text": r.evidence_text,
                }
                for r in rel_rows
            ]

        return nodes, edges

    def query_multihop(
        self,
        db: Session,
        query: str,
        mission_filter: Optional[str] = None,
    ) -> dict:
        """Answer multi-hop KG queries (e.g. 'missions with propulsion anomalies and corrective actions') with citations."""
        profile = extract_problem_entities(query)
        q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))

        stmt = (
            select(MissionIncident, Document, DocumentChunk, DocumentSection)
            .join(Document, Document.id == MissionIncident.document_id)
            .join(DocumentChunk, DocumentChunk.id == MissionIncident.chunk_id)
            .outerjoin(DocumentSection, DocumentSection.id == MissionIncident.section_id)
        )
        if mission_filter:
            stmt = stmt.where(MissionIncident.mission == mission_filter)

        rows = db.execute(stmt).all()
        if not rows:
            return {
                "answer": ABSTENTION_MESSAGE,
                "abstained": True,
                "matched_subsystems": profile.subsystems,
                "paths": [],
                "citations": [],
            }

        scored_paths: list[tuple[float, KGPathResult]] = []
        for inc, doc, chunk, sec in rows:
            blob = (
                f"{inc.mission} {inc.subsystem} {inc.component or ''} "
                f"{inc.anomaly_title} {inc.anomaly_description} {inc.root_cause} "
                f"{inc.corrective_action} {inc.failure_mechanism or ''}"
            ).lower()

            score = 0.0
            if profile.subsystems:
                if inc.subsystem in profile.subsystems:
                    score += 2.0
            if profile.mechanisms and inc.failure_mechanism in profile.mechanisms:
                score += 1.5

            for kw in profile.keywords:
                if kw in blob:
                    score += 0.6

            blob_tokens = set(re.findall(r"[a-z0-9]+", blob))
            overlap = len(q_tokens & blob_tokens)
            score += 0.2 * overlap

            # If query specifically targets a subsystem (e.g., propulsion) and score < 1.5, skip noise
            if profile.subsystems and inc.subsystem not in profile.subsystems and score < 1.8:
                continue
            if score < 0.8:
                continue

            cit = CitationOut(
                document_id=doc.id,
                doc_code=doc.doc_code,
                document_title=doc.title,
                source_url=doc.source_url,
                licence=doc.licence,
                section_id=inc.section_id,
                section=sec.title if sec else "Document Body",
                page_number=inc.page_number,
                chunk_id=inc.chunk_id,
                quote=inc.evidence_text,
                bbox_json=list(chunk.bbox_json or []),
                verified=inc.verification_status == "verified",
            )
            scored_paths.append(
                (
                    score,
                    KGPathResult(
                        mission=inc.mission,
                        subsystem=inc.subsystem,
                        component=inc.component,
                        anomaly=inc.anomaly_title,
                        root_cause=inc.root_cause,
                        corrective_action=inc.corrective_action,
                        verification_status=inc.verification_status,
                        citation=cit,
                    ),
                )
            )

        if not scored_paths:
            return {
                "answer": ABSTENTION_MESSAGE,
                "abstained": True,
                "matched_subsystems": profile.subsystems,
                "paths": [],
                "citations": [],
            }

        scored_paths.sort(key=lambda item: item[0], reverse=True)
        top_paths = [p for _s, p in scored_paths[:8]]

        lines: list[str] = []
        citations: list[CitationOut] = []
        for p in top_paths:
            c = p.citation
            citations.append(c)
            lines.append(
                f"• {p.mission} ({p.subsystem}) — Anomaly: {p.anomaly}. "
                f"Root cause: {p.root_cause} "
                f"Corrective action: {p.corrective_action} "
                f"[{c.doc_code} · p.{c.page_number} · {c.section}]"
            )

        return {
            "answer": "\n".join(lines),
            "abstained": False,
            "matched_subsystems": profile.subsystems,
            "paths": [
                {
                    "mission": p.mission,
                    "subsystem": p.subsystem,
                    "component": p.component,
                    "anomaly": p.anomaly,
                    "root_cause": p.root_cause,
                    "corrective_action": p.corrective_action,
                    "verification_status": p.verification_status,
                    "citation": p.citation.model_dump(mode="json"),
                }
                for p in top_paths
            ],
            "citations": [c.model_dump(mode="json") for c in citations],
        }
