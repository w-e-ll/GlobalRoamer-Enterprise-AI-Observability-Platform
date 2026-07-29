"""Enable pgvector extension.

Revision ID: b74439911c47
Revises: 15ef6de8fe59
Create Date: 2026-07-29 17:51:28.963197
"""

from collections.abc import Sequence

from alembic import op


revision: str = "b74439911c47"
down_revision: str | None = "15ef6de8fe59"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable the pgvector PostgreSQL extension."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Disable the pgvector PostgreSQL extension."""
    op.execute("DROP EXTENSION IF EXISTS vector")
