import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.ports.trace_repository import (
    TraceRepository,
)
from globalroamer_platform.domain.entities.trace import Trace
from globalroamer_platform.domain.models.processing_status import (
    ProcessingStatus,
)
from globalroamer_platform.infrastructure.database.models import (
    TraceModel,
)


logger = logging.getLogger(__name__)


class SQLAlchemyTraceRepository(TraceRepository):
    """SQLAlchemy implementation of the TraceRepository port."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, trace: Trace) -> Trace:
        logger.debug(
            "Persisting trace internal_id=%s",
            trace.id,
        )

        model = self._to_model(trace)

        self._session.add(model)

        await self._session.flush()
        await self._session.refresh(model)

        logger.info(
            "Trace persisted internal_id=%s version=%d",
            model.id,
            model.version,
        )

        return self._to_domain(model)

    async def get_by_id(
        self,
        trace_id: UUID,
    ) -> Trace | None:

        logger.debug(
            "Loading trace by internal_id=%s",
            trace_id,
        )

        model = await self._session.get(
            TraceModel,
            trace_id,
        )

        if model is None:
            logger.debug(
                "Trace not found internal_id=%s",
                trace_id,
            )
            return None

        logger.debug(
            "Trace loaded internal_id=%s",
            model.id,
        )

        return self._to_domain(model)

    async def get_by_external_id(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> Trace | None:

        logger.debug(
            "Loading trace by external identifier tenant_id=%s trace_id=%s",
            tenant_id,
            trace_id,
        )

        stmt = (
            select(TraceModel)
            .where(TraceModel.tenant_id == tenant_id)
            .where(TraceModel.trace_id == trace_id)
        )

        result = await self._session.execute(stmt)

        model = result.scalar_one_or_none()

        if model is None:
            logger.debug(
                "Trace not found tenant_id=%s trace_id=%s",
                tenant_id,
                trace_id,
            )
            return None

        logger.debug(
            "Trace loaded internal_id=%s",
            model.id,
        )

        return self._to_domain(model)

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Trace]:

        logger.debug(
            "Listing traces tenant_filter=%s limit=%d offset=%d",
            tenant_id or "-",
            limit,
            offset,
        )

        stmt = select(TraceModel)

        if tenant_id is not None:
            stmt = stmt.where(
                TraceModel.tenant_id == tenant_id
            )

        stmt = (
            stmt
            .offset(offset)
            .limit(limit)
            .order_by(TraceModel.created_at.desc())
        )

        result = await self._session.execute(stmt)

        models = result.scalars().all()

        logger.debug(
            "Retrieved %d traces from database",
            len(models),
        )

        return [
            self._to_domain(model)
            for model in models
        ]

    async def update(
        self,
        trace: Trace,
    ) -> Trace:

        logger.debug(
            "Updating trace internal_id=%s version=%d",
            trace.id,
            trace.version,
        )

        model = await self._session.get(
            TraceModel,
            trace.id,
        )

        if model is None:
            logger.warning(
                "Cannot update trace because it does not exist "
                "internal_id=%s",
                trace.id,
            )
            raise ValueError("Trace not found")

        model.status = trace.status.value
        model.current_stage = trace.current_stage
        model.version = trace.version
        model.updated_at = trace.updated_at

        await self._session.flush()
        await self._session.refresh(model)

        logger.info(
            "Trace updated internal_id=%s status=%s "
            "current_stage=%s version=%d",
            model.id,
            model.status,
            model.current_stage,
            model.version,
        )

        return self._to_domain(model)

    @staticmethod
    def _to_domain(
        model: TraceModel,
    ) -> Trace:

        return Trace(
            id=model.id,
            tenant_id=model.tenant_id,
            trace_id=model.trace_id,
            testcase_id=model.testcase_id,
            status=ProcessingStatus(model.status),
            current_stage=model.current_stage,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(
        trace: Trace,
    ) -> TraceModel:

        return TraceModel(
            id=trace.id,
            tenant_id=trace.tenant_id,
            trace_id=trace.trace_id,
            testcase_id=trace.testcase_id,
            status=trace.status.value,
            current_stage=trace.current_stage,
            version=trace.version,
            created_at=trace.created_at,
            updated_at=trace.updated_at,
        )
