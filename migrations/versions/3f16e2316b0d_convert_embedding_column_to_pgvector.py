"""Convert embedding column to pgvector.

Revision ID: REPLACE_WITH_GENERATED_REVISION
Revises: b74439911c47
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision = "3f16e2316b0d"
down_revision: str | None = "b74439911c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert the embedding array to PostgreSQL's vector type."""
    op.alter_column(
        "embedding_records",
        "embedding",
        existing_type=postgresql.ARRAY(sa.Double()),
        type_=Vector(),
        existing_nullable=False,
        postgresql_using="embedding::vector",
    )


def downgrade() -> None:
    """Convert the pgvector value back to a double-precision array."""
    op.alter_column(
        "embedding_records",
        "embedding",
        existing_type=Vector(),
        type_=postgresql.ARRAY(sa.Double()),
        existing_nullable=False,
        postgresql_using=(
            "string_to_array("
            "trim(both '[]' from embedding::text), "
            "','"
            ")::double precision[]"
        ),
    )
