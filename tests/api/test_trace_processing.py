from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEST_CONFIGURATION_FILE = (
    PROJECT_ROOT
    / "tests"
    / "config"
    / "globalroamer_ai_test.yml"
)

TRACE_MAPPING_FILE = (
    PROJECT_ROOT
    / "etc"
    / "trace_mapping.yml"
)


# Application configuration is loaded while globalroamer_platform.main is
# imported, so all relevant environment variables must be defined first.
os.environ["CONFIG_FILE"] = str(
    TEST_CONFIGURATION_FILE
)

os.environ["TRACE_MAPPING_CONFIGURATION_PATH"] = str(
    TRACE_MAPPING_FILE
)


# main.py eagerly constructs the production embedding provider during import.
# API tests must not download or initialize a real Sentence Transformers model,
# so patch the composition-root factory before importing the FastAPI app.
_test_embedding_provider = MagicMock()
_test_embedding_provider.model_name = "test-embedding-model"
_test_embedding_provider.model_version = "test"

with patch(
    "globalroamer_platform.bootstrap.embedding_provider."
    "build_embedding_provider",
    return_value=_test_embedding_provider,
):
    from globalroamer_platform.api.dependencies.trace_processing import (  # noqa: E402
        get_process_trace,
    )
    from globalroamer_platform.application.traces.process_trace import (  # noqa: E402
        ProcessTraceResult,
    )
    from globalroamer_platform.main import app  # noqa: E402


client = TestClient(app)


def test_process_trace_missing_file_returns_400() -> None:
    """A missing trace file produces a client error."""

    response = client.post(
        "/api/v1/traces/process",
        json={
            "source_path": "missing.csv",
            "tenant_id": "smoke-test",
            "trace_id": "missing-trace",
        },
    )

    assert response.status_code == 400

    body = response.json()

    assert "detail" in body
    assert "missing.csv" in body["detail"]


def test_process_trace_success() -> None:
    """A valid request returns the ProcessTrace use-case result."""

    use_case = AsyncMock()

    use_case.execute.return_value = ProcessTraceResult(
        parsed_trace_id=(
            "11111111-1111-1111-1111-111111111111"
        ),
        tenant_id="smoke-test",
        trace_id="pytest-trace",
        testcase_id="pytest-trace",
        row_count=3,
        evidence_count=1,
        signal_count=9,
        extracted_value_count=2,
        mapped_value_count=6,
        warning_count=6,
        error_count=0,
        is_valid=True,
        is_complete=False,
    )

    app.dependency_overrides[
        get_process_trace
    ] = lambda: use_case

    try:
        response = client.post(
            "/api/v1/traces/process",
            json={
                "source_path": "sample_trace.csv",
                "tenant_id": "smoke-test",
                "trace_id": "pytest-trace",
                "testcase_id": "pytest-trace",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201

    body = response.json()

    assert (
        body["parsed_trace_id"]
        == "11111111-1111-1111-1111-111111111111"
    )
    assert body["tenant_id"] == "smoke-test"
    assert body["trace_id"] == "pytest-trace"
    assert body["testcase_id"] == "pytest-trace"
    assert body["row_count"] == 3
    assert body["evidence_count"] == 1
    assert body["signal_count"] == 9
    assert body["extracted_value_count"] == 2
    assert body["mapped_value_count"] == 6
    assert body["warning_count"] == 6
    assert body["error_count"] == 0
    assert body["is_valid"] is True
    assert body["is_complete"] is False

    use_case.execute.assert_awaited_once()

    command = use_case.execute.await_args.args[0]

    assert command.source_path == Path(
        "sample_trace.csv"
    )
    assert command.tenant_id == "smoke-test"
    assert command.trace_id == "pytest-trace"
    assert command.testcase_id == "pytest-trace"


def test_process_trace_validation_error() -> None:
    """An empty request fails FastAPI request validation."""

    response = client.post(
        "/api/v1/traces/process",
        json={},
    )

    assert response.status_code == 422

    body = response.json()

    assert "detail" in body
