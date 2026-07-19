# globalroamer_platform/infrastructure/database/models.py

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from globalroamer_platform.domain.models.processing_status import (
    ProcessingStatus,
)
from globalroamer_platform.infrastructure.database.base import Base


class TraceRecord(Base):
    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "trace_id",
            name="uq_traces_tenant_trace",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
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

    testcase_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ProcessingStatus.RECEIVED.value,
        index=True,
    )

    current_stage: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ingestion",
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
