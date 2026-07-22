"""SQLAlchemy persistence store for embedding records."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.domain.models.embedding_record import (
    EmbeddingRecord,
)
from globalroamer_platform.infrastructure.database.models import (
    EmbeddingRecordModel,
)
from globalroamer_platform.infrastructure.persistence.embedding_record_mapper import (
    EmbeddingRecordMapper,
)


class EmbeddingRecordStore:
    """
    Persistence gateway for EmbeddingRecord domain objects.

    The caller owns the transaction. This store never commits or rolls back.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        if not isinstance(session, AsyncSession):
            raise TypeError(
                "session must be an AsyncSession"
            )

        self._session = session

    async def save_many(
        self,
        records: Sequence[EmbeddingRecord],
    ) -> None:
        """
        Add multiple embedding records to the current transaction.

        An empty sequence is accepted and performs no operation.
        """

        if isinstance(records, (str, bytes)):
            raise TypeError(
                "records must be a sequence of EmbeddingRecord objects"
            )

        if not isinstance(records, Sequence):
            raise TypeError(
                "records must be a sequence of EmbeddingRecord objects"
            )

        record_tuple = tuple(records)

        for record in record_tuple:
            if not isinstance(record, EmbeddingRecord):
                raise TypeError(
                    "all records must be EmbeddingRecord objects"
                )

        if not record_tuple:
            return

        models = tuple(
            EmbeddingRecordMapper.to_model(record)
            for record in record_tuple
        )

        self._session.add_all(
            list(models)
        )

    async def get_by_id(
        self,
        record_id: UUID,
    ) -> EmbeddingRecord | None:
        """Return one embedding record by UUID."""

        if not isinstance(record_id, UUID):
            raise TypeError(
                "record_id must be a UUID"
            )

        model = await self._session.get(
            EmbeddingRecordModel,
            record_id,
        )

        if model is None:
            return None

        return EmbeddingRecordMapper.to_domain(
            model
        )

    async def list_by_trace(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> tuple[EmbeddingRecord, ...]:
        """Return all embedding records for one tenant trace."""

        self._validate_required_string(
            tenant_id,
            field_name="tenant_id",
        )
        self._validate_required_string(
            trace_id,
            field_name="trace_id",
        )

        statement = (
            select(EmbeddingRecordModel)
            .where(
                EmbeddingRecordModel.tenant_id == tenant_id,
                EmbeddingRecordModel.trace_id == trace_id,
            )
            .order_by(
                EmbeddingRecordModel.created_at,
                EmbeddingRecordModel.id,
            )
        )

        result = await self._session.execute(
            statement
        )

        return tuple(
            EmbeddingRecordMapper.to_domain(model)
            for model in result.scalars().all()
        )

    async def list_by_chunk(
        self,
        *,
        tenant_id: str,
        chunk_id: UUID,
    ) -> tuple[EmbeddingRecord, ...]:
        """Return all embeddings generated for one chunk."""

        self._validate_required_string(
            tenant_id,
            field_name="tenant_id",
        )

        if not isinstance(chunk_id, UUID):
            raise TypeError(
                "chunk_id must be a UUID"
            )

        statement = (
            select(EmbeddingRecordModel)
            .where(
                EmbeddingRecordModel.tenant_id == tenant_id,
                EmbeddingRecordModel.chunk_id == chunk_id,
            )
            .order_by(
                EmbeddingRecordModel.model_name,
                EmbeddingRecordModel.model_version,
                EmbeddingRecordModel.id,
            )
        )

        result = await self._session.execute(
            statement
        )

        return tuple(
            EmbeddingRecordMapper.to_domain(model)
            for model in result.scalars().all()
        )

    async def get_by_chunk_and_model(
        self,
        *,
        tenant_id: str,
        chunk_id: UUID,
        model_name: str,
        model_version: str,
    ) -> EmbeddingRecord | None:
        """Return the embedding for one chunk and model identity."""

        self._validate_required_string(
            tenant_id,
            field_name="tenant_id",
        )
        self._validate_required_string(
            model_name,
            field_name="model_name",
        )
        self._validate_required_string(
            model_version,
            field_name="model_version",
        )

        if not isinstance(chunk_id, UUID):
            raise TypeError(
                "chunk_id must be a UUID"
            )

        statement = select(
            EmbeddingRecordModel
        ).where(
            EmbeddingRecordModel.tenant_id == tenant_id,
            EmbeddingRecordModel.chunk_id == chunk_id,
            EmbeddingRecordModel.model_name == model_name,
            EmbeddingRecordModel.model_version == model_version,
        )

        result = await self._session.execute(
            statement
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return EmbeddingRecordMapper.to_domain(
            model
        )

    @staticmethod
    def _validate_required_string(
        value: object,
        *,
        field_name: str,
    ) -> None:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string"
            )

        if not value.strip():
            raise ValueError(
                f"{field_name} must not be empty"
            )
