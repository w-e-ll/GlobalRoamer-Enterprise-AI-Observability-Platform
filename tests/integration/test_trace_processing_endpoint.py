from __future__ import annotations

from uuid import uuid4

import httpx


API_BASE_URL = "http://localhost:8000"
PROCESS_TRACE_ENDPOINT = "/api/v1/traces/process"


def test_process_trace_endpoint_success() -> None:
    unique_id = uuid4().hex

    payload = {
        "source_path": "sample_trace.csv",
        "tenant_id": "integration-test",
        "trace_id": f"integration-{unique_id}",
        "testcase_id": f"integration-{unique_id}",
    }

    response = httpx.post(
        f"{API_BASE_URL}{PROCESS_TRACE_ENDPOINT}",
        json=payload,
        timeout=30.0,
    )

    assert response.status_code == 201, response.text

    body = response.json()

    assert body["tenant_id"] == payload["tenant_id"]
    assert body["trace_id"] == payload["trace_id"]
    assert body["testcase_id"] == payload["testcase_id"]

    assert body["row_count"] == 3
    assert body["evidence_count"] >= 0
    assert body["signal_count"] >= 0
    assert body["extracted_value_count"] >= 0
    assert body["mapped_value_count"] >= 0

    assert body["warning_count"] >= 0
    assert body["error_count"] == 0

    assert body["is_valid"] is True
    assert isinstance(body["is_complete"], bool)

    assert body["parsed_trace_id"]


def test_process_trace_endpoint_missing_file_returns_400() -> None:
    unique_id = uuid4().hex

    response = httpx.post(
        f"{API_BASE_URL}{PROCESS_TRACE_ENDPOINT}",
        json={
            "source_path": f"missing-{unique_id}.csv",
            "tenant_id": "integration-test",
            "trace_id": f"missing-{unique_id}",
        },
        timeout=30.0,
    )

    assert response.status_code == 400, response.text

    body = response.json()

    assert "detail" in body
    assert f"missing-{unique_id}.csv" in body["detail"]
