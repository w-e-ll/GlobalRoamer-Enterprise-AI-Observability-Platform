"""Mapping between embedding domain records and SQLAlchemy models."""

from __future__ import annotations

from globalroamer_platform.domain.models.embedding_record import (
    EmbeddingRecord,
)
from globalroamer_platform.infrastructure.database.models import (
    EmbeddingRecordModel,
)


class EmbeddingRecordMapper:
    """
    Convert between EmbeddingRecord domain objects and persistence models.

    The mapper contains no transaction or database-query logic.
    """

    @staticmethod
    def to_model(
        record: EmbeddingRecord,
    ) -> EmbeddingRecordModel:
        """Convert a domain embedding record into an ORM model."""

        if not isinstance(record, EmbeddingRecord):
            raise TypeError(
                "record must be an EmbeddingRecord"
            )

        return EmbeddingRecordModel(
            id=record.id,
            tenant_id=record.tenant_id,
            trace_id=record.trace_id,
            testcase_id=record.testcase_id,
            chunk_id=record.chunk_id,
            model_name=record.model_name,
            model_version=record.model_version,
            dimensions=record.dimensions,
            embedding=list(record.embedding),
            content_checksum=record.content_checksum,
            created_at=record.created_at,
        )

    @staticmethod
    def to_domain(
        model: EmbeddingRecordModel,
    ) -> EmbeddingRecord:
        """Convert an ORM embedding model into a domain object."""

        if not isinstance(model, EmbeddingRecordModel):
            raise TypeError(
                "model must be an EmbeddingRecordModel"
            )

        return EmbeddingRecord(
            id=model.id,
            tenant_id=model.tenant_id,
            trace_id=model.trace_id,
            testcase_id=model.testcase_id,
            chunk_id=model.chunk_id,
            model_name=model.model_name,
            model_version=model.model_version,
            dimensions=model.dimensions,
            embedding=tuple(
                float(value)
                for value in model.embedding
            ),
            content_checksum=model.content_checksum,
            created_at=model.created_at,
        )
