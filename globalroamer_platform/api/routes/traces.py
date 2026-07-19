import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from globalroamer_platform.api.dependencies.repositories import (
    get_trace_repository,
)
from globalroamer_platform.api.schemas.trace import (
    CreateTraceRequest,
    TraceListResponse,
    TraceResponse,
)
from globalroamer_platform.application.ports.trace_repository import (
    TraceRepository,
)
from globalroamer_platform.application.traces.create_trace import (
    CreateTrace,
    CreateTraceCommand,
    TraceAlreadyExistsError,
)
from globalroamer_platform.application.traces.get_trace import (
    GetTrace,
    TraceNotFoundError,
)
from globalroamer_platform.application.traces.list_traces import (
    InvalidTracePaginationError,
    ListTraces,
    ListTracesQuery,
)
from globalroamer_platform.core.logging import (
    stage_context,
    tenant_id_context,
    trace_id_context,
)


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/traces",
    tags=["traces"],
)


TraceRepositoryDependency = Annotated[
    TraceRepository,
    Depends(get_trace_repository),
]


@router.post(
    "",
    response_model=TraceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a trace",
)
async def create_trace(
    request: CreateTraceRequest,
    repository: TraceRepositoryDependency,
) -> TraceResponse:
    """Create a new tenant-scoped trace."""

    tenant_id = request.tenant_id.strip()
    external_trace_id = request.trace_id.strip()
    testcase_id = request.testcase_id.strip()

    tenant_token = tenant_id_context.set(tenant_id)
    trace_token = trace_id_context.set(external_trace_id)
    stage_token = stage_context.set("api.create_trace")

    try:
        logger.info(
            "Create trace request received testcase_id=%s",
            testcase_id,
        )

        use_case = CreateTrace(repository)

        command = CreateTraceCommand(
            tenant_id=tenant_id,
            trace_id=external_trace_id,
            testcase_id=testcase_id,
        )

        try:
            trace = await use_case.execute(command)
        except TraceAlreadyExistsError as exc:
            logger.warning(
                "Trace creation rejected because trace already exists"
            )

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        logger.info(
            "Trace created internal_id=%s status=%s "
            "current_stage=%s version=%d",
            trace.id,
            trace.status.value,
            trace.current_stage,
            trace.version,
        )

        return TraceResponse.from_domain(trace)

    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unexpected error while creating trace"
        )
        raise
    finally:
        stage_context.reset(stage_token)
        trace_id_context.reset(trace_token)
        tenant_id_context.reset(tenant_token)


@router.get(
    "/{trace_id}",
    response_model=TraceResponse,
    summary="Get a trace",
)
async def get_trace(
    trace_id: UUID,
    repository: TraceRepositoryDependency,
) -> TraceResponse:
    """Retrieve one trace by its internal UUID."""

    stage_token = stage_context.set("api.get_trace")
    lookup_trace_token = trace_id_context.set(str(trace_id))

    tenant_token = None
    external_trace_token = None

    try:
        logger.info(
            "Get trace request received internal_id=%s",
            trace_id,
        )

        use_case = GetTrace(repository)

        try:
            trace = await use_case.execute(trace_id)
        except TraceNotFoundError as exc:
            logger.warning(
                "Trace was not found internal_id=%s",
                trace_id,
            )

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

        tenant_token = tenant_id_context.set(trace.tenant_id)
        external_trace_token = trace_id_context.set(trace.trace_id)

        logger.info(
            "Trace retrieved internal_id=%s status=%s "
            "current_stage=%s version=%d",
            trace.id,
            trace.status.value,
            trace.current_stage,
            trace.version,
        )

        return TraceResponse.from_domain(trace)

    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unexpected error while retrieving trace "
            "internal_id=%s",
            trace_id,
        )
        raise
    finally:
        if external_trace_token is not None:
            trace_id_context.reset(external_trace_token)

        if tenant_token is not None:
            tenant_id_context.reset(tenant_token)

        trace_id_context.reset(lookup_trace_token)
        stage_context.reset(stage_token)


@router.get(
    "",
    response_model=TraceListResponse,
    summary="List traces",
)
async def list_traces(
    repository: TraceRepositoryDependency,
    tenant_id: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=100,
            description="Filter traces by tenant identifier.",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=ListTraces.MAX_LIMIT,
            description="Maximum number of traces to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of traces to skip.",
        ),
    ] = 0,
) -> TraceListResponse:
    """Retrieve traces using optional tenant filtering and pagination."""

    normalized_tenant_id = (
        tenant_id.strip()
        if tenant_id is not None
        else None
    )

    tenant_token = tenant_id_context.set(
        normalized_tenant_id or "-"
    )
    stage_token = stage_context.set("api.list_traces")

    try:
        logger.info(
            "List traces request received limit=%d offset=%d",
            limit,
            offset,
        )

        use_case = ListTraces(repository)

        try:
            traces = await use_case.execute(
                ListTracesQuery(
                    tenant_id=normalized_tenant_id,
                    limit=limit,
                    offset=offset,
                )
            )
        except InvalidTracePaginationError as exc:
            logger.warning(
                "Invalid trace pagination parameters "
                "limit=%d offset=%d error=%s",
                limit,
                offset,
                exc,
            )

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        logger.info(
            "Trace list retrieved result_count=%d "
            "limit=%d offset=%d",
            len(traces),
            limit,
            offset,
        )

        return TraceListResponse(
            items=[
                TraceResponse.from_domain(trace)
                for trace in traces
            ]
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unexpected error while listing traces "
            "limit=%d offset=%d",
            limit,
            offset,
        )
        raise
    finally:
        stage_context.reset(stage_token)
        tenant_id_context.reset(tenant_token)
