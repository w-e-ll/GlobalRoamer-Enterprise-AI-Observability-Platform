"""SQLAlchemy model for transactional outbox messages."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from globalroamer_platform.infrastructure.database.base import Base


class OutboxMessageModel(Base):
    """Database representation of a durable outbox message."""

    __tablename__ = "outbox_messages"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )

    event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        unique=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    event_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    correlation_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    causation_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    producer: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        Index(
            "ix_outbox_messages_status_available_at",
            "status",
            "available_at",
        ),
        Index(
            "ix_outbox_messages_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_outbox_messages_correlation_id",
            "correlation_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            "OutboxMessageModel("
            f"id={self.id!r}, "
            f"event_id={self.event_id!r}, "
            f"event_type={self.event_type!r}, "
            f"status={self.status!r}, "
            f"attempt_count={self.attempt_count!r}"
            ")"
        )
