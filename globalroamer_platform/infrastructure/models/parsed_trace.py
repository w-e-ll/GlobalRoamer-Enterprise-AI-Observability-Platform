from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from globalroamer_platform.infrastructure.database.base import Base


class ParsedTraceModel(Base):
    """
    SQLAlchemy persistence model for ParsedTrace.

    The complete ParsedTrace aggregate is currently stored as JSON to keep
    the persistence layer decoupled from the evolving parsing domain model.
    """

    __tablename__ = "parsed_traces"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    trace_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    testcase_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    evidence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    signal_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    extracted_value_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    mapped_value_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    warning_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    is_valid: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    is_complete: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    parsed_trace_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
