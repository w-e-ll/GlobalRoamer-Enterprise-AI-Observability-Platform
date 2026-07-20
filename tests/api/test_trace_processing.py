from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]

os.environ["CONFIG_FILE"] = str(
    PROJECT_ROOT
    / "tests"
    / "config"
    / "globalroamer_ai_test.yml"
)

os.environ["TRACE_MAPPING_CONFIGURATION_PATH"] = str(
    PROJECT_ROOT / "etc" / "trace_mapping.yml"
)

from globalroamer_platform.api.dependencies.trace_processing import (  # noqa: E402
    get_process_trace,
)
from globalroamer_platform.application.traces.process_trace import (  # noqa: E402
    ProcessTraceResult,
)
from globalroamer_platform.main import app  # noqa: E402


client = TestClient(app)


def test_process_trace_missing_file_returns_400() -> None:
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
    use_case = AsyncMock()

    use_case.execute.return_value = ProcessTraceResult(
        parsed_trace_id="11111111-1111-1111-1111-111111111111",
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

    app.dependency_overrides[get_process_trace] = lambda: use_case

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

    assert body["tenant_id"] == "smoke-test"
    assert body["trace_id"] == "pytest-trace"
    assert body["row_count"] == 3
    assert body["mapped_value_count"] == 6
    assert body["error_count"] == 0

    use_case.execute.assert_awaited_once()

    command = use_case.execute.await_args.args[0]

    assert command.source_path == Path("sample_trace.csv")
    assert command.tenant_id == "smoke-test"
    assert command.trace_id == "pytest-trace"
    assert command.testcase_id == "pytest-trace"

def test_process_trace_validation_error() -> None:
    response = client.post(
        "/api/v1/traces/process",
        json={},
    )

    assert response.status_code == 422
