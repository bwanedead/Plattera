from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .schema import (
    CanonicalTraceEvent,
    CanonicalTraceRecord,
    CompletenessStatus,
    LoopFamily,
    RawTraceEvent,
    TRACE_VERSION,
    TerminalSnapshot,
    TimestampSource,
)

_MAX_NORMALIZATION_WARNINGS = 32
_MAX_MISSING_COMPONENTS = 32


def build_canonical_trace(
    *,
    trace_id: str,
    run_id: str,
    session_id: str | None,
    request_id: str | None,
    loop_family: LoopFamily,
    request_metadata: dict[str, Any],
    start_context_summary: dict[str, Any],
    started_at_epoch_seconds: int,
    events: list[dict[str, Any] | RawTraceEvent],
    terminal: dict[str, Any] | TerminalSnapshot,
    completeness_status: CompletenessStatus = "complete",
    missing_components: Iterable[str] | None = None,
    normalization_warnings: Iterable[str] | None = None,
    trace_version: str = TRACE_VERSION,
) -> CanonicalTraceRecord:
    missing = _normalize_components(missing_components)
    warnings = _normalize_warnings(normalization_warnings)
    final_completeness = _resolve_completeness(
        completeness_status=completeness_status,
        missing_components=missing,
        warnings=warnings,
    )
    normalized_events = _normalize_events(
        trace_id=trace_id,
        started_at_epoch_seconds=started_at_epoch_seconds,
        events=events,
        warnings=warnings,
    )
    terminal_snapshot = (
        terminal if isinstance(terminal, TerminalSnapshot) else TerminalSnapshot.model_validate(terminal)
    )
    return CanonicalTraceRecord(
        trace_id=trace_id,
        run_id=run_id,
        session_id=session_id,
        request_id=request_id,
        loop_family=loop_family,
        request_metadata=request_metadata,
        start_context_summary=start_context_summary,
        started_at_epoch_seconds=started_at_epoch_seconds,
        events=normalized_events,
        terminal=terminal_snapshot,
        completeness_status=final_completeness,
        missing_components=missing,
        normalization_warnings=warnings,
        trace_version=trace_version,
    )


def _normalize_events(
    *,
    trace_id: str,
    started_at_epoch_seconds: int,
    events: list[dict[str, Any] | RawTraceEvent],
    warnings: list[str],
) -> list[CanonicalTraceEvent]:
    staged: list[dict[str, Any]] = []
    for source_idx, raw in enumerate(events):
        parsed = raw if isinstance(raw, RawTraceEvent) else RawTraceEvent.model_validate(raw)
        event = parsed.model_dump(mode="json")
        source_origin = event.get("source_origin")
        if not isinstance(source_origin, dict):
            source_origin = {"kind": "unknown", "ref": "unknown", "sequence_index": source_idx}
            event["source_origin"] = source_origin
            _push_warning(warnings, "source_origin_missing_defaulted")
        sequence_index = source_origin.get("sequence_index")
        if not isinstance(sequence_index, int) or sequence_index < 0:
            source_origin["sequence_index"] = source_idx
            _push_warning(warnings, "source_sequence_index_invalid_defaulted")
        timestamp = event.get("timestamp_epoch_seconds")
        if not isinstance(timestamp, int) or timestamp < 0:
            source_sequence = _source_sequence_key(event, source_idx)
            event["timestamp_epoch_seconds"] = int(started_at_epoch_seconds + source_sequence)
            _set_payload_timestamp_source(event=event, value="derived_sequence")
            _push_warning(warnings, "event_timestamp_derived_sequence")
        else:
            _set_payload_timestamp_source(event=event, value="source")
        staged.append({"source_idx": source_idx, "event": event})

    staged.sort(
        key=lambda row: (
            int(row["event"]["timestamp_epoch_seconds"]),
            int(_source_sequence_key(row["event"], int(row["source_idx"]))),
            int(_source_priority(row["event"])),
            int(row["source_idx"]),
        )
    )

    out: list[CanonicalTraceEvent] = []
    for idx, row in enumerate(staged):
        event = row["event"]
        event["event_index"] = idx
        event["event_id"] = f"{trace_id}:e{idx:04d}"
        out.append(CanonicalTraceEvent.model_validate(event))
    return out


def _set_payload_timestamp_source(*, event: dict[str, Any], value: TimestampSource) -> None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {}
        event["payload"] = payload
    payload["timestamp_source"] = value


def _resolve_completeness(
    *,
    completeness_status: CompletenessStatus,
    missing_components: list[str],
    warnings: list[str],
) -> CompletenessStatus:
    if missing_components and completeness_status != "partial":
        _push_warning(warnings, "completeness_auto_partial_due_to_missing_components")
        return "partial"
    return completeness_status


def _normalize_components(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    out: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in out:
            continue
        out.append(value)
        if len(out) >= _MAX_MISSING_COMPONENTS:
            break
    return out


def _normalize_warnings(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    out: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        out.append(value)
        if len(out) >= _MAX_NORMALIZATION_WARNINGS:
            break
    return out


def _push_warning(warnings: list[str], warning: str) -> None:
    if len(warnings) >= _MAX_NORMALIZATION_WARNINGS:
        return
    warnings.append(str(warning))


def _source_priority(event: dict[str, Any]) -> int:
    event_kind = str(event.get("event_kind") or "").strip().lower()
    if event_kind == "request_start":
        return 0
    return 1


def _source_sequence_key(event: dict[str, Any], fallback: int) -> int:
    source_origin = event.get("source_origin")
    if isinstance(source_origin, dict):
        value = source_origin.get("sequence_index")
        if isinstance(value, int) and value >= 0:
            return value
    return fallback
