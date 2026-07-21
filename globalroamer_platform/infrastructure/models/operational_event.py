from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import (
    ARRAY,
    JSONB,
    UUID,
)
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from globalroamer_platform.infrastructure.database.base import Base
from globalroamer_platform.infrastructure.database.models import (
    utc_now,
)


class OperationalEventModel(Base):
    """
    SQLAlchemy persistence model for normalized OperationalEvent objects.

    Each row represents one canonical operational event produced from
    ParsedTrace normalization.
    """

    __tablename__ = "operational_events"

    __table_args__ = (
        Index(
            "ix_operational_events_tenant_trace",
            "tenant_id",
            "trace_id",
        ),
        Index(
            "ix_operational_events_trace_sequence",
            "trace_id",
            "sequence_number",
        ),
        Index(
            "ix_operational_events_event_name",
            "event_name",
        ),
        Index(
            "ix_operational_events_event_family",
            "event_family",
        ),
        Index(
            "ix_operational_events_severity",
            "severity",
        ),
        Index(
            "ix_operational_events_timestamp",
            "timestamp",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
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

    testcase_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    event_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    event_family: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    raw_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    normalized_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source_line_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    protocol_layer: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    direction: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    result: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    workflow_stage: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    network_domain: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    operator: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    country: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    cause: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    retry_recommended: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    recommendation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )

    evidence_lines: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
    )

    extracted_values: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    event_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
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
