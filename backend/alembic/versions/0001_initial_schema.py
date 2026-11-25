"""Initial MISSIONWISE AI schema with pgvector, pg_trgm, and all provenance tables.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-25 15:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 1. Roles & Users & Audit
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(128), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    # 2. Documents, Versions, Sections, Chunks, Embeddings
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_code", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("licence", sa.String(255), nullable=False),
        sa.Column("org", sa.String(128), nullable=False),
        sa.Column("mission", sa.String(255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("ingestion_status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_doc_code", "documents", ["doc_code"])
    op.create_index("ix_documents_org", "documents", ["org"])
    op.create_index("ix_documents_mission", "documents", ["mission"])
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])

    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])

    op.create_table(
        "document_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_sections.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_leaf", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("section_path", sa.String(128), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_document_sections_document_id", "document_sections", ["document_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("bbox_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', coalesce(text, ''))", persisted=True),
            nullable=True,
        ),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_section_id", "document_chunks", ["section_id"])
    op.create_index("ix_document_chunks_page_number", "document_chunks", ["page_number"])
    op.create_index(
        "ix_document_chunks_tsv_gin", "document_chunks", ["tsv"], postgresql_using="gin"
    )

    op.create_table(
        "document_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_document_embeddings_hnsw",
        "document_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # 3. STAIR, Retrieval Logs, Conversations, Messages, Citations
    op.create_table(
        "stair_training_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("toc_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("split", sa.String(32), nullable=False, server_default="train"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stair_training_pairs_document_id", "stair_training_pairs", ["document_id"])

    op.create_table(
        "retrieval_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("mission_scope", sa.String(255), nullable=True),
        sa.Column("stair_level", sa.String(32), nullable=False, server_default="L1"),
        sa.Column("selected_section_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stage_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("top_rerank_score", sa.Float(), nullable=True),
        sa.Column("confidence_category", sa.String(32), nullable=False, server_default="None"),
        sa.Column("abstained", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        sa.Column("reranker_model", sa.String(255), nullable=False),
        sa.Column("llm_model", sa.String(255), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_retrieval_logs_request_id", "retrieval_logs", ["request_id"])

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("mission_scope", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "retrieval_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retrieval_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(32), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("abstained", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("claims_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
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
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("claim_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "evidence_classification",
            sa.String(64),
            nullable=False,
            server_default="explicitly_stated",
        ),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_citations_message_id", "citations", ["message_id"])
    op.create_index("ix_citations_document_id", "citations", ["document_id"])
    op.create_index("ix_citations_chunk_id", "citations", ["chunk_id"])

    # 4. Failure Chains & Engineering Knowledge Graph
    op.create_table(
        "mission_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
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
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mission_entities_entity_type", "mission_entities", ["entity_type"])
    op.create_index("ix_mission_entities_name", "mission_entities", ["name"])
    op.create_index("ix_mission_entities_normalized_name", "mission_entities", ["normalized_name"])

    op.create_table(
        "failure_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mission", sa.String(255), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("event_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timestamp_label", sa.String(128), nullable=True),
        sa.Column("subsystem", sa.String(255), nullable=True),
        sa.Column(
            "evidence_classification",
            sa.String(64),
            nullable=False,
            server_default="explicitly_stated",
        ),
        sa.Column("verification_status", sa.String(32), nullable=False, server_default="pending"),
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
    op.create_index("ix_failure_events_mission", "failure_events", ["mission"])
    op.create_index("ix_failure_events_document_id", "failure_events", ["document_id"])

    op.create_table(
        "failure_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("failure_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("failure_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("verification_status", sa.String(32), nullable=False, server_default="pending"),
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
            "evidence_chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_failure_relationships_source_event_id", "failure_relationships", ["source_event_id"])
    op.create_index("ix_failure_relationships_target_event_id", "failure_relationships", ["target_event_id"])

    op.create_table(
        "corrective_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mission", sa.String(255), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("subsystem", sa.String(255), nullable=True),
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
    op.create_index("ix_corrective_actions_mission", "corrective_actions", ["mission"])


def downgrade() -> None:
    op.drop_table("corrective_actions")
    op.drop_table("failure_relationships")
    op.drop_table("failure_events")
    op.drop_table("mission_entities")
    op.drop_table("citations")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("retrieval_logs")
    op.drop_table("stair_training_pairs")
    op.drop_table("document_embeddings")
    op.drop_table("document_chunks")
    op.drop_table("document_sections")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("audit_logs")
    op.drop_table("users")
    op.drop_table("roles")
