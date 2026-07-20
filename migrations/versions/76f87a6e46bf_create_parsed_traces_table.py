"""create parsed traces table

Revision ID: 76f87a6e46bf
Revises: 5330ff620be8
Create Date: 2026-07-20 15:02:22.978780
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '76f87a6e46bf'
down_revision: str | None = '5330ff620be8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parsed_traces",
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
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "ended_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "duration_seconds",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "row_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "evidence_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "signal_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "extracted_value_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "mapped_value_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "warning_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "error_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "is_valid",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "is_complete",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "parsed_trace_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_parsed_traces",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "trace_id",
            name="uq_parsed_traces_tenant_trace",
        ),
    )

    op.create_index(
        "ix_parsed_traces_tenant_id",
        "parsed_traces",
        ["tenant_id"],
        unique=False,
    )

    op.create_index(
        "ix_parsed_traces_trace_id",
        "parsed_traces",
        ["trace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_parsed_traces_trace_id",
        table_name="parsed_traces",
    )

    op.drop_index(
        "ix_parsed_traces_tenant_id",
        table_name="parsed_traces",
    )

    op.drop_table("parsed_traces")
