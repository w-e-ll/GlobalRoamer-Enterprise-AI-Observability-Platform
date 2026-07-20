from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.domain.models.parsed_trace import ParsedTrace
from globalroamer_platform.infrastructure.models.parsed_trace import (
    ParsedTraceModel,
)


class ParsedTraceStore:
    """
    PostgreSQL persistence gateway for immutable ParsedTrace snapshots.

    ParsedTrace is stored as a complete JSON document together with selected
    summary fields used for filtering, monitoring, and operational queries.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
            self,
            parsed_trace: ParsedTrace,
    ) -> ParsedTraceModel:
        """
        Insert or update a parsed trace identified by tenant_id and trace_id.

        The method does not commit the transaction. Transaction ownership
        remains with the caller.
        """
        tenant_id, trace_id, _ = self._identity(parsed_trace)

        model = await self._get_model(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

        values = self._to_model_values(parsed_trace)

        if model is None:
            model = ParsedTraceModel(**values)
            self._session.add(model)
        else:
            self._update_model(model, values)

        await self._session.flush()
        await self._session.refresh(model)

        return model

    async def get(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> ParsedTraceModel | None:
        """
        Return a stored parsed trace snapshot.
        """
        return await self._get_model(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

    async def exists(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> bool:
        """
        Check whether a parsed trace snapshot exists.
        """
        statement = (
            select(ParsedTraceModel.id)
            .where(ParsedTraceModel.tenant_id == tenant_id)
            .where(ParsedTraceModel.trace_id == trace_id)
            .limit(1)
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none() is not None

    async def list_by_tenant(
        self,
        *,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ParsedTraceModel]:
        """
        Return parsed trace snapshots for one tenant, newest first.
        """
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        if offset < 0:
            raise ValueError("offset must not be negative")

        statement = (
            select(ParsedTraceModel)
            .where(ParsedTraceModel.tenant_id == tenant_id)
            .order_by(ParsedTraceModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(statement)

        return result.scalars().all()

    async def delete(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> bool:
        """
        Delete a parsed trace snapshot.

        Returns True when a row was deleted.
        """
        statement = (
            delete(ParsedTraceModel)
            .where(ParsedTraceModel.tenant_id == tenant_id)
            .where(ParsedTraceModel.trace_id == trace_id)
            .returning(ParsedTraceModel.id)
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none() is not None

    async def _get_model(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> ParsedTraceModel | None:
        statement = (
            select(ParsedTraceModel)
            .where(ParsedTraceModel.tenant_id == tenant_id)
            .where(ParsedTraceModel.trace_id == trace_id)
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none()

    @classmethod
    def _to_model_values(
            cls,
            parsed_trace: ParsedTrace,
    ) -> dict:
        tenant_id, trace_id, testcase_id = cls._identity(
            parsed_trace,
        )

        payload = parsed_trace.to_dict()

        return {
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "testcase_id": testcase_id,
            "started_at": parsed_trace.started_at,
            "ended_at": parsed_trace.ended_at,
            "duration_seconds": parsed_trace.duration_seconds,
            "row_count": parsed_trace.row_count,
            "evidence_count": parsed_trace.evidence_count,
            "signal_count": parsed_trace.signal_count,
            "extracted_value_count": (
                parsed_trace.extracted_value_count
            ),
            "mapped_value_count": (
                parsed_trace.mapped_value_count
            ),
            "warning_count": len(parsed_trace.warnings),
            "error_count": len(parsed_trace.errors),
            "is_valid": parsed_trace.is_valid,
            "is_complete": parsed_trace.is_complete,
            "parsed_trace_json": payload,
        }

    @staticmethod
    def _update_model(
        model: ParsedTraceModel,
        values: dict,
    ) -> None:
        for field_name, value in values.items():
            setattr(model, field_name, value)

    @staticmethod
    def _identity(
            parsed_trace: ParsedTrace,
    ) -> tuple[str, str, str | None]:
        metadata = parsed_trace.metadata

        tenant_id = metadata.get("tenant_id")
        trace_id = metadata.get("trace_id")
        testcase_id = metadata.get("testcase_id")

        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError(
                "ParsedTrace metadata must contain a non-empty tenant_id"
            )

        if not isinstance(trace_id, str) or not trace_id.strip():
            raise ValueError(
                "ParsedTrace metadata must contain a non-empty trace_id"
            )

        if testcase_id is not None and not isinstance(
                testcase_id,
                str,
        ):
            raise ValueError(
                "ParsedTrace metadata testcase_id must be a string or None"
            )

        return (
            tenant_id.strip(),
            trace_id.strip(),
            testcase_id.strip()
            if isinstance(testcase_id, str)
            else None,
        )
