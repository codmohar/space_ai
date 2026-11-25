"""Add event_type column to failure_events.

Revision ID: 0003_failure_event_type
Revises: 0002_stair_review_and_toc_fields
Create Date: 2026-11-25 16:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_failure_event_type"
down_revision = "0002_stair_review_and_toc_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "failure_events",
        sa.Column("event_type", sa.String(64), nullable=False, server_default="anomaly"),
    )


def downgrade() -> None:
    op.drop_column("failure_events", "event_type")
