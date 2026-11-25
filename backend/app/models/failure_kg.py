"""Failure chain reconstruction, incident index, and Engineering Knowledge Graph models (Postgres v1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MissionEntity(Base):
    __tablename__ = "mission_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # mission | subsystem | component | anomaly | root_cause | corrective_action
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class MissionEntityRelation(Base):
    """Typed, provenance-backed edges connecting MissionEntity nodes in the Engineering KG."""

    __tablename__ = "mission_entity_relations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mission_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mission_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # has_subsystem | has_component | experienced_anomaly | caused_by | mitigated_by
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class FailureEvent(Base):
    __tablename__ = "failure_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="anomaly")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp_label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    subsystem: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    evidence_classification: Mapped[str] = mapped_column(
        String(64), nullable=False, default="explicitly_stated"
    )
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | verified | rejected
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class FailureRelationship(Base):
    __tablename__ = "failure_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("failure_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("failure_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # caused_by | contributed_to | preceded_by | associated_with | reported_as
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | verified | rejected
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    subsystem: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class MissionIncident(Base):
    """Structured anomaly/incident record extracted from reports with full provenance."""

    __tablename__ = "mission_incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subsystem: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    component: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    anomaly_title: Mapped[str] = mapped_column(String(512), nullable=False)
    anomaly_description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    consequence: Mapped[str] = mapped_column(Text, nullable=False)
    corrective_action: Mapped[str] = mapped_column(Text, nullable=False)
    failure_mechanism: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    evidence_classification: Mapped[str] = mapped_column(
        String(64), nullable=False, default="explicitly_stated"
    )
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | verified | rejected
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384), nullable=True)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(mission, '') || ' ' || coalesce(subsystem, '') || ' ' || coalesce(anomaly_title, '') || ' ' || coalesce(anomaly_description, '') || ' ' || coalesce(root_cause, '') || ' ' || coalesce(corrective_action, ''))",
            persisted=True,
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_mission_incidents_tsv_gin", "tsv", postgresql_using="gin"),
        Index(
            "ix_mission_incidents_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
