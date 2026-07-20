"""FastAPI routes for trace-processing operations.

This module exposes the application-level trace-processing workflow through
HTTP.

The route is responsible only for:

* validating the HTTP request;
* creating the application command;
* invoking the ProcessTrace use case;
* translating the application result into an HTTP response.

Trace loading, parsing, mapping, persistence, and transaction handling remain
inside the application, domain, dependency, and infrastructure layers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from globalroamer_platform.core.exceptions import TraceLoaderError
from globalroamer_platform.api.dependencies.trace_processing import (
    get_process_trace,
)
from globalroamer_platform.api.schemas.trace_processing import (
    ProcessTraceRequest,
    ProcessTraceResponse,
)
from globalroamer_platform.application.traces.process_trace import (
    ProcessTrace,
    ProcessTraceCommand,
    ProcessTraceResult,
)


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/traces",
    tags=["Trace Processing"],
)


ProcessTraceDependency = Annotated[
    ProcessTrace,
    Depends(get_process_trace),
]


@router.post(
    "/process",
    response_model=ProcessTraceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process and persist a trace",
    description=(
        "Loads a trace artifact, parses and normalizes its contents, extracts "
        "evidence, signals, and values, applies configured mappings, and "
        "persists the parsed trace in PostgreSQL."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": (
                "The trace-processing request or source artifact is invalid."
            ),
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "The requested source artifact does not exist.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "The trace-processing workflow failed.",
        },
    },
)
async def process_trace(
    request: ProcessTraceRequest,
    use_case: ProcessTraceDependency,
) -> ProcessTraceResponse:
    """Process and persist one trace artifact.

    Args:
        request: Validated trace-processing HTTP request.
        use_case: Injected ProcessTrace application service.

    Returns:
        Summary of the persisted parsed trace.

    Raises:
        HTTPException: If the source file cannot be found, the request is
            invalid, or processing fails unexpectedly.
    """
    source_path = Path(request.source_path)

    logger.info(
        "Trace processing request received",
        extra={
            "tenant_id": request.tenant_id,
            "trace_id": request.trace_id,
            "testcase_id": request.testcase_id,
            "source_path": str(source_path),
            "stage": "api.process_trace",
        },
    )

    try:
        command = ProcessTraceCommand(
            source_path=source_path,
            tenant_id=request.tenant_id,
            trace_id=request.trace_id,
            testcase_id=request.testcase_id,
        )

        result = await use_case.execute(
            command,
        )

    except FileNotFoundError as exc:
        logger.warning(
            "Trace source artifact not found",
            extra={
                "tenant_id": request.tenant_id,
                "trace_id": request.trace_id,
                "testcase_id": request.testcase_id,
                "source_path": str(source_path),
                "stage": "api.process_trace",
                "error_type": type(exc).__name__,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trace source artifact was not found.",
        ) from exc

    except (ValueError, IsADirectoryError, PermissionError) as exc:
        logger.warning(
            "Trace processing request rejected",
            extra={
                "tenant_id": request.tenant_id,
                "trace_id": request.trace_id,
                "testcase_id": request.testcase_id,
                "source_path": str(source_path),
                "stage": "api.process_trace",
                "error_type": type(exc).__name__,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except TraceLoaderError as exc:
        logger.warning(
            "Trace source artifact rejected",
            extra={
                "tenant_id": request.tenant_id,
                "trace_id": request.trace_id,
                "testcase_id": request.testcase_id,
                "source_path": str(source_path),
                "stage": "api.process_trace",
                "error_type": type(exc).__name__,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Trace processing workflow failed",
            extra={
                "tenant_id": request.tenant_id,
                "trace_id": request.trace_id,
                "testcase_id": request.testcase_id,
                "source_path": str(source_path),
                "stage": "api.process_trace",
                "error_type": type(exc).__name__,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Trace processing failed.",
        ) from exc

    logger.info(
        "Trace processing request completed",
        extra={
            "parsed_trace_id": str(result.parsed_trace_id),
            "tenant_id": result.tenant_id,
            "trace_id": result.trace_id,
            "testcase_id": result.testcase_id,
            "row_count": result.row_count,
            "evidence_count": result.evidence_count,
            "signal_count": result.signal_count,
            "extracted_value_count": result.extracted_value_count,
            "mapped_value_count": result.mapped_value_count,
            "warning_count": result.warning_count,
            "error_count": result.error_count,
            "is_valid": result.is_valid,
            "is_complete": result.is_complete,
            "stage": "api.process_trace",
        },
    )

    return _to_response(
        result,
    )


def _to_response(
    result: ProcessTraceResult,
) -> ProcessTraceResponse:
    """Convert an application result into an API response.

    Args:
        result: Result returned by the ProcessTrace use case.

    Returns:
        Public trace-processing response schema.
    """
    return ProcessTraceResponse(
        parsed_trace_id=result.parsed_trace_id,
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
        row_count=result.row_count,
        evidence_count=result.evidence_count,
        signal_count=result.signal_count,
        extracted_value_count=result.extracted_value_count,
        mapped_value_count=result.mapped_value_count,
        warning_count=result.warning_count,
        error_count=result.error_count,
        is_valid=result.is_valid,
        is_complete=result.is_complete,
    )
