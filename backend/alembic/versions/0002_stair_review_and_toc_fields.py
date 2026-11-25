"""Add extraction_method to document_sections and review fields to stair_training_pairs.

Revision ID: 0002_stair_review_and_toc_fields
Revises: 0001_initial_schema
Create Date: 2026-11-25 16:05:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_stair_review_and_toc_fields"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_sections",
        sa.Column(
            "extraction_method",
            sa.String(32),
            nullable=False,
            server_default="pdf_outline",
        ),
    )
    op.add_column(
        "stair_training_pairs",
        sa.Column(
            "reviewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "stair_training_pairs",
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stair_training_pairs", "reviewer_notes")
    op.drop_column("stair_training_pairs", "reviewed")
    op.drop_column("document_sections", "extraction_method")
