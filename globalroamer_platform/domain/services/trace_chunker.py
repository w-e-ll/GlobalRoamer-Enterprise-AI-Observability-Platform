#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from typing import Any

from globalroamer_ai.core.exceptions import TraceChunkingError

logger = logging.getLogger("trace_chunker")


def chunk_normalized_trace(
        normalized_trace: dict[str, Any],
        chunk_size: int = 4000,
        chunk_overlap: int = 400
) -> list[dict[str, Any]]:
    try:
        trace_id = extract_trace_id(normalized_trace)
        events = extract_events(normalized_trace)

        chunks = []
        current_lines = []
        current_events = []
        current_size = 0
        chunk_index = 0

        for event in events:
            event_text = event_to_text(event)
            event_size = len(event_text)

            if current_size + event_size > chunk_size and current_lines:
                chunks.append(build_chunk(trace_id, chunk_index, current_lines, current_events, normalized_trace))
                chunk_index += 1
                current_lines = build_overlap_lines(current_lines, chunk_overlap)
                current_events = current_events[-max(1, len(current_events) // 10):]
                current_size = sum(len(line) for line in current_lines)

            current_lines.append(event_text)
            current_events.append(event)
            current_size += event_size

        if current_lines:
            chunks.append(build_chunk(trace_id, chunk_index, current_lines, current_events, normalized_trace))

        logger.info(f"Created {len(chunks)} chunks for trace {trace_id}")

        return chunks

    except Exception as exc:
        trace_id = normalized_trace.get("trace_id") or normalized_trace.get("testcase_id") or "unknown"
        logger.error(f"Failed to chunk trace {trace_id}: {exc}")
        raise TraceChunkingError(f"Failed to chunk trace: {trace_id}")


def extract_trace_id(normalized_trace: dict[str, Any]) -> str:
    if normalized_trace.get("trace_id"):
        return str(normalized_trace["trace_id"])

    if normalized_trace.get("testcase_id"):
        return str(normalized_trace["testcase_id"])

    source = normalized_trace.get("source") or {}

    if isinstance(source, dict) and source.get("testcase_id"):
        return str(source["testcase_id"])

    events = extract_events(normalized_trace)

    if events and events[0].get("testcase_id"):
        return str(events[0]["testcase_id"])

    return "unknown_trace"


def extract_events(normalized_trace: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(normalized_trace, list):
        return normalized_trace

    if isinstance(normalized_trace.get("normalized_events"), list):
        return normalized_trace["normalized_events"]

    if isinstance(normalized_trace.get("events"), list):
        return normalized_trace["events"]

    if isinstance(normalized_trace.get("operational_events"), list):
        return normalized_trace["operational_events"]

    return []


def event_to_text(event: dict[str, Any]) -> str:
    tags = event.get("tags") or []
    metadata = event.get("metadata") or {}
    extracted_values = event.get("extracted_values") or {}

    tag_text = ", ".join(str(tag) for tag in tags)
    metadata_text = compact_dict(metadata)
    extracted_text = compact_dict(extracted_values)

    return (
        f"testcase_id={event.get('testcase_id')} | "
        f"event_id={event.get('event_id')} | "
        f"timestamp={event.get('timestamp')} | "
        f"family={event.get('event_family')} | "
        f"protocol_layer={event.get('protocol_layer')} | "
        f"name={event.get('event_name')} | "
        f"severity={event.get('severity')} | "
        f"result={event.get('result')} | "
        f"operator={event.get('operator')} | "
        f"country={event.get('country')} | "
        f"domain={event.get('network_domain')} | "
        f"workflow_stage={event.get('workflow_stage')} | "
        f"direction={event.get('direction')} | "
        f"cause={event.get('cause')} | "
        f"retry_recommended={event.get('retry_recommended')} | "
        f"recommendation={event.get('recommendation')} | "
        f"message={event.get('normalized_message')} | "
        f"tags=[{tag_text}] | "
        f"metadata=[{metadata_text}] | "
        f"extracted_values=[{extracted_text}] | "
        f"raw={event.get('raw_message')}"
    )


def build_chunk(
        trace_id: str,
        chunk_index: int,
        lines: list[str],
        events: list[dict[str, Any]],
        normalized_trace: dict[str, Any]
) -> dict[str, Any]:
    chunk_text = "\n".join(lines)

    event_names = sorted(set(str(event.get("event_name")) for event in events if event.get("event_name")))
    event_families = sorted(set(str(event.get("event_family")) for event in events if event.get("event_family")))
    severities = sorted(set(str(event.get("severity")) for event in events if event.get("severity")))
    causes = sorted(set(str(event.get("cause")) for event in events if event.get("cause")))
    operators = sorted(set(str(event.get("operator")) for event in events if event.get("operator")))
    countries = sorted(set(str(event.get("country")) for event in events if event.get("country")))
    domains = sorted(set(str(event.get("network_domain")) for event in events if event.get("network_domain")))

    tags = sorted(set(str(tag) for event in events for tag in event.get("tags", []) if tag))

    metadata = extract_source_metadata(normalized_trace, events)

    return {
        "chunk_id": f"{trace_id}::chunk_{chunk_index}",
        "trace_id": trace_id,
        "testcase_id": trace_id,
        "chunk_index": chunk_index,
        "text": chunk_text,
        "event_count": len(events),
        "event_ids": [event.get("event_id") for event in events if event.get("event_id")],
        "event_names": event_names,
        "event_families": event_families,
        "severities": severities,
        "causes": causes,
        "operators": operators,
        "countries": countries,
        "network_domains": domains,
        "tags": tags,
        "source_trace": metadata.get("source_trace"),
        "source_result": metadata.get("source_result"),
        "source_report": metadata.get("source_report"),
        "has_high_severity": "high" in severities or "critical" in severities,
        "has_failure": any(event.get("result") == "failed" for event in events),
        "has_retry_recommended": any(bool(event.get("retry_recommended")) for event in events),
    }


def extract_source_metadata(normalized_trace: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    source = normalized_trace.get("source") or {}

    if isinstance(source, dict):
        source_trace = source.get("trace_path")
        source_result = source.get("result_path")
        source_report = source.get("report_path")
    else:
        source_trace = None
        source_result = None
        source_report = None

    if not source_trace and events:
        source_trace = events[0].get("source_trace")

    return {
        "source_trace": source_trace,
        "source_result": source_result,
        "source_report": source_report,
    }


def build_overlap_lines(lines: list[str], overlap_chars: int) -> list[str]:
    if overlap_chars <= 0:
        return []

    overlap = []
    total = 0

    for line in reversed(lines):
        overlap.insert(0, line)
        total += len(line)

        if total >= overlap_chars:
            break

    return overlap


def compact_dict(data: dict[str, Any]) -> str:
    if not data:
        return ""

    items = []

    for key, value in data.items():
        if value is None:
            continue

        if isinstance(value, (dict, list)):
            continue

        items.append(f"{key}={value}")

    return ", ".join(items)
