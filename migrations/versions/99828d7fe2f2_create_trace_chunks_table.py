"""create trace_chunks table

Revision ID: 99828d7fe2f2
Revises: 0a027abbf53f
Create Date: 2026-07-21 18:17:04.952134
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "99828d7fe2f2"
down_revision: str | None = "0a027abbf53f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trace_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "trace_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "testcase_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "text",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "event_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "event_ids",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "event_names",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "event_families",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "severities",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "causes",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "has_failure",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "has_high_severity",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "has_retry_recommended",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_trace_chunks",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "trace_id",
            "chunk_index",
            name="uq_trace_chunks_tenant_trace_chunk_index",
        ),
    )

    op.create_index(
        "ix_trace_chunks_tenant_trace",
        "trace_chunks",
        [
            "tenant_id",
            "trace_id",
        ],
        unique=False,
    )

    op.create_index(
        "ix_trace_chunks_content_hash",
        "trace_chunks",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trace_chunks_content_hash",
        table_name="trace_chunks",
    )

    op.drop_index(
        "ix_trace_chunks_tenant_trace",
        table_name="trace_chunks",
    )

    op.drop_table("trace_chunks")
