"""Add corpus_metadata table for atomic corpus_version tracking.

Revision ID: 0006_corpus_version
Revises: 0005_classify_and_jobs
Create Date: 2026-11-26 01:52:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_corpus_version"
down_revision = "0005_classify_and_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corpus_metadata",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    # Seed initial row
    op.execute(
        "INSERT INTO corpus_metadata (version, document_count, chunk_count) "
        "SELECT 1, (SELECT COUNT(*) FROM documents), (SELECT COUNT(*) FROM document_chunks);"
    )


def downgrade() -> None:
    op.drop_table("corpus_metadata")
