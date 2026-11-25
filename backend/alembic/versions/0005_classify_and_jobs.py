"""Add classification to documents and create ingestion_jobs table.

Revision ID: 0005_classify_and_jobs
Revises: 0004_incidents_and_kg_edges
Create Date: 2026-11-25 19:42:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_classify_and_jobs"
down_revision = "0004_incidents_and_kg_edges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add classification to documents
    op.add_column(
        "documents",
        sa.Column("classification", sa.String(32), nullable=False, server_default="public"),
    )
    op.create_index(
        "ix_documents_classification",
        "documents",
        ["classification"],
        unique=False,
    )

    # 2. Add summary to conversations
    op.add_column(
        "conversations",
        sa.Column("summary", sa.Text(), nullable=True),
    )

    # 3. Create ingestion_jobs table
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("doc_code", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(32), nullable=False, server_default="pdf"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("logs", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ingestion_jobs_job_id", "ingestion_jobs", ["job_id"], unique=True)
    op.create_index("ix_ingestion_jobs_doc_code", "ingestion_jobs", ["doc_code"], unique=False)
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_documents_classification", table_name="documents")
    op.drop_column("documents", "classification")
