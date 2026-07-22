from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy import Float

from globalroamer_platform.infrastructure.database.base import Base

from sqlalchemy.dialects.postgresql import (
    JSONB,
    UUID as PostgreSQLUUID,
)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class TraceModel(Base):
    """SQLAlchemy persistence model for a trace."""

    __tablename__ = "traces"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "trace_id",
            name="uq_traces_tenant_trace",
        ),
        Index("ix_traces_status", "status"),
        Index("ix_traces_tenant_id", "tenant_id"),
        Index("ix_traces_testcase_id", "testcase_id"),
        Index("ix_traces_trace_id", "trace_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    trace_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    testcase_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    current_stage: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class TraceChunkModel(Base):
    """
    SQLAlchemy persistence model for an immutable TraceChunk.

    Domain tuples are stored as PostgreSQL JSONB arrays. Conversion between
    this persistence representation and the TraceChunk domain model belongs
    in TraceChunkMapper.
    """

    __tablename__ = "trace_chunks"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "trace_id",
            "chunk_index",
            name="uq_trace_chunks_tenant_trace_index",
        ),
        Index(
            "ix_trace_chunks_tenant_trace",
            "tenant_id",
            "trace_id",
        ),
        Index(
            "ix_trace_chunks_content_hash",
            "content_hash",
        ),
        Index(
            "ix_trace_chunks_created_at",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    trace_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    testcase_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    event_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    event_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    event_names: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    event_families: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    severities: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    causes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    has_failure: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    has_high_severity: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    has_retry_recommended: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            "TraceChunkModel("
            f"id={self.id!r}, "
            f"tenant_id={self.tenant_id!r}, "
            f"trace_id={self.trace_id!r}, "
            f"chunk_index={self.chunk_index!r}, "
            f"event_count={self.event_count!r}"
            ")"
        )


class EmbeddingRecordModel(Base):
    """Persisted vector embedding generated from one trace chunk."""

    __tablename__ = "embedding_records"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "chunk_id",
            "model_name",
            "model_version",
            name=(
                "uq_embedding_records_"
                "tenant_chunk_model_version"
            ),
        ),
        Index(
            "ix_embedding_records_tenant_trace",
            "tenant_id",
            "trace_id",
        ),
        Index(
            "ix_embedding_records_tenant_chunk",
            "tenant_id",
            "chunk_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    trace_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    testcase_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    chunk_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "trace_chunks.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    model_version: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    embedding: Mapped[list[float]] = mapped_column(
        ARRAY(Float),
        nullable=False,
    )

    content_checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
