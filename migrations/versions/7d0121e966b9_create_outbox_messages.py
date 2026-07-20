"""create outbox messages

Revision ID: 7d0121e966b9
Revises: 76f87a6e46bf
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "7d0121e966b9"
down_revision: str | None = "76f87a6e46bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "event_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "correlation_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "causation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "producer",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            name="uq_outbox_messages_event_id",
        ),
    )

    op.create_index(
        "ix_outbox_messages_status_available_at",
        "outbox_messages",
        ["status", "available_at"],
        unique=False,
    )

    op.create_index(
        "ix_outbox_messages_tenant_created_at",
        "outbox_messages",
        ["tenant_id", "created_at"],
        unique=False,
    )

    op.create_index(
        "ix_outbox_messages_correlation_id",
        "outbox_messages",
        ["correlation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_messages_correlation_id",
        table_name="outbox_messages",
    )

    op.drop_index(
        "ix_outbox_messages_tenant_created_at",
        table_name="outbox_messages",
    )

    op.drop_index(
        "ix_outbox_messages_status_available_at",
        table_name="outbox_messages",
    )

    op.drop_table("outbox_messages")
