"""Add mission_incidents and mission_entity_relations tables for Phase 5.

Revision ID: 0004_incidents_and_kg_edges
Revises: 0003_failure_event_type
Create Date: 2026-11-25 17:10:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0004_incidents_and_kg_edges"
down_revision = "0003_failure_event_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mission", sa.String(255), nullable=False),
        sa.Column("subsystem", sa.String(255), nullable=False),
        sa.Column("component", sa.String(255), nullable=True),
        sa.Column("anomaly_title", sa.String(512), nullable=False),
        sa.Column("anomaly_description", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("consequence", sa.Text(), nullable=False),
        sa.Column("corrective_action", sa.Text(), nullable=False),
        sa.Column("failure_mechanism", sa.String(255), nullable=True),
        sa.Column(
            "evidence_classification",
            sa.String(64),
            nullable=False,
            server_default="explicitly_stated",
        ),
        sa.Column(
            "verification_status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_sections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(mission, '') || ' ' || coalesce(subsystem, '') || ' ' || coalesce(anomaly_title, '') || ' ' || coalesce(anomaly_description, '') || ' ' || coalesce(root_cause, '') || ' ' || coalesce(corrective_action, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mission_incidents_mission", "mission_incidents", ["mission"])
    op.create_index("ix_mission_incidents_subsystem", "mission_incidents", ["subsystem"])
    op.create_index(
        "ix_mission_incidents_failure_mechanism",
        "mission_incidents",
        ["failure_mechanism"],
    )
    op.create_index("ix_mission_incidents_document_id", "mission_incidents", ["document_id"])
    op.create_index("ix_mission_incidents_chunk_id", "mission_incidents", ["chunk_id"])
    op.create_index(
        "ix_mission_incidents_tsv_gin",
        "mission_incidents",
        ["tsv"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_mission_incidents_hnsw",
        "mission_incidents",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "mission_entity_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mission_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mission_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_sections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_mission_entity_relations_source_entity_id",
        "mission_entity_relations",
        ["source_entity_id"],
    )
    op.create_index(
        "ix_mission_entity_relations_target_entity_id",
        "mission_entity_relations",
        ["target_entity_id"],
    )
    op.create_index(
        "ix_mission_entity_relations_relation_type",
        "mission_entity_relations",
        ["relation_type"],
    )
    op.create_index(
        "ix_mission_entity_relations_document_id",
        "mission_entity_relations",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_table("mission_entity_relations")
    op.drop_table("mission_incidents")
