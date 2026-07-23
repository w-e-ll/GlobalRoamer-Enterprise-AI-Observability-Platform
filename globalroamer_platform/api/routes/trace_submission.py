"""FastAPI route for asynchronous trace submission."""

import logging
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status

from globalroamer_platform.api.dependencies.trace_submission import get_submit_trace
from globalroamer_platform.api.schemas.trace_submission import (
    SubmitTraceRequest,
    SubmitTraceResponse,
)
from globalroamer_platform.application.traces.submit_trace import (
    SubmitTrace,
    SubmitTraceCommand,
    SubmitTraceResult,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/traces",
    tags=["Trace Submission"],
)

SubmitTraceDependency = Annotated[
    SubmitTrace,
    Depends(get_submit_trace),
]


@router.post(
    "/submit",
    response_model=SubmitTraceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_trace(
    payload: SubmitTraceRequest,
    request: Request,
    use_case: SubmitTraceDependency,
) -> SubmitTraceResponse:
    correlation_id = (
        request.headers.get("X-Correlation-ID")
        or str(uuid4())
    )

    command = SubmitTraceCommand(
        source_path=Path(payload.source_path),
        tenant_id=payload.tenant_id,
        trace_id=payload.trace_id,
        testcase_id=payload.testcase_id,
        correlation_id=correlation_id,
    )

    logger.info(
        "Trace submission request received",
        extra={
            "correlation_id": correlation_id,
            "tenant_id": command.tenant_id,
            "trace_id": command.trace_id,
            "testcase_id": command.testcase_id,
            "source_path": str(command.source_path),
            "stage": "api.submit_trace",
        },
    )

    result = await use_case.execute(command)

    logger.info(
        "Trace submission accepted",
        extra={
            "submission_event_id": str(result.submission_event_id),
            "outbox_message_id": str(result.outbox_message_id),
            "correlation_id": result.correlation_id,
            "tenant_id": result.tenant_id,
            "trace_id": result.trace_id,
            "testcase_id": result.testcase_id,
            "stage": "api.submit_trace",
        },
    )

    return _to_response(result)


def _to_response(result: SubmitTraceResult) -> SubmitTraceResponse:
    return SubmitTraceResponse(
        submission_event_id=result.submission_event_id,
        outbox_message_id=result.outbox_message_id,
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
        correlation_id=result.correlation_id,
        status=result.status,
    )
