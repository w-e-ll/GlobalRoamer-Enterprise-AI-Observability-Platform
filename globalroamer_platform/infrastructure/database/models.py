from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from globalroamer_platform.infrastructure.database.base import Base


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
