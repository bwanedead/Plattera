from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ...terminal_taxonomy import classify_transcript_edit_terminal
from ..builder import build_canonical_trace
from ..schema import CanonicalTraceRecord, RawTraceEvent, TerminalSnapshot
from .transcript_edit_helpers import (
    as_dict,
    as_dict_list,
    closure_payload,
    event_actor,
    event_kind,
    event_reason_code,
    event_status,
    payload_for_stream_event,
    refs_delta,
    as_int,
    as_str,
    first_non_empty,
    source_local_id,
    source_ref,
)

_PROGRESS_LOG_LIMIT = 40
_CRITICAL_EVENT_LIMIT = 200

_SOURCE_KIND_PROGRESS = "tx_progress_log"
_SOURCE_KIND_CRITICAL = "tx_critical_events"
_SOURCE_KIND_BLOCKER_HISTORY = "tx_blocker_registry_history"
_SOURCE_KIND_BLOCKER_ROWS = "tx_blocker_registry_rows"
_SOURCE_KIND_HITL_STATE = "tx_runtime_hitl_state"
_SOURCE_KIND_TERMINAL = "tx_terminal_summary"


def build_transcript_edit_trace(
    *,
    run_snapshot: dict[str, Any],
    snapshot_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    run_entry, snapshot = _resolve_run_payload(run_snapshot)
    run_id = first_non_empty(snapshot.get("run_id"), run_entry.get("run_id"), "unknown_tx_run")
    session_id = first_non_empty(snapshot.get("session_id"), None)
    request_id = first_non_empty(run_id, session_id, "unknown_request")
    progress_log = as_dict_list(snapshot.get("progress_log"))
    critical_events = as_dict_list(snapshot.get("critical_events"))
    runtime_hitl_state = as_dict(snapshot.get("runtime_hitl_state"))
    terminal_summary = as_dict(snapshot.get("terminal_summary"))
    blocker_registry = as_dict(runtime_hitl_state.get("blocker_registry"))
    trace_identifier = trace_id or _default_trace_id(
        run_id=run_id,
        snapshot_ref=snapshot_ref,
        progress_log=progress_log,
        critical_events=critical_events,
    )
    started_at_epoch_seconds = _first_event_timestamp(progress_log, critical_events) or 0

    missing_components: list[str] = []
    warnings: list[str] = []
    if len(progress_log) >= _PROGRESS_LOG_LIMIT:
        missing_components.append("tx_progress_log_history")
        warnings.append("tx_progress_log_bounded")
    if len(critical_events) >= _CRITICAL_EVENT_LIMIT:
        missing_components.append("tx_critical_events_history")
        warnings.append("tx_critical_events_bounded")
    if not terminal_summary:
        missing_components.append("tx_terminal_summary")
        warnings.append("tx_terminal_summary_missing")
    if not blocker_registry:
        missing_components.append("tx_blocker_registry_lifecycle")
        warnings.append("tx_blocker_registry_missing")

    ledger_snapshot = _extract_ledger_snapshot(progress_log=progress_log, critical_events=critical_events, terminal_summary=terminal_summary)
    if not ledger_snapshot:
        missing_components.append("decision_ledger_closure_source")
        warnings.append("decision_ledger_missing_for_closure_truth")

    raw_events = _map_stream_events(
        events=progress_log,
        source_kind=_SOURCE_KIND_PROGRESS,
        source_ref_value=source_ref(primary=snapshot_ref, default=f"run:{run_id}"),
        start_sequence=0,
    )
    raw_events.extend(
        _map_stream_events(
            events=critical_events,
            source_kind=_SOURCE_KIND_CRITICAL,
            source_ref_value=source_ref(primary=snapshot_ref, default=f"run:{run_id}"),
            start_sequence=len(progress_log),
        )
    )
    raw_events.extend(
        _synth_iteration_events(
            progress_log=progress_log,
            source_ref_value=source_ref(primary=snapshot_ref, default=f"run:{run_id}"),
            start_sequence=len(progress_log) + len(critical_events) + 2000,
        )
    )
    raw_events.extend(
        _map_blocker_registry_events(
            blocker_registry=blocker_registry,
            source_ref_value=source_ref(primary=snapshot_ref, default=f"run:{run_id}"),
            start_sequence=len(progress_log) + len(critical_events),
        )
    )
    raw_events.extend(
        _map_hitl_state_events(
            runtime_hitl_state=runtime_hitl_state,
            source_ref_value=source_ref(primary=snapshot_ref, default=f"run:{run_id}"),
            start_sequence=len(progress_log) + len(critical_events) + 5000,
        )
    )

    terminal_snapshot = _map_terminal_snapshot(
        status=as_str(snapshot.get("status")) or as_str(run_entry.get("status")),
        reason_code=as_str(snapshot.get("reason_code")),
        terminal_summary=terminal_summary,
        ledger_snapshot=ledger_snapshot,
    )
    terminal_payload = {
        "status": as_str(snapshot.get("status")) or as_str(run_entry.get("status")),
        "reason_code": as_str(snapshot.get("reason_code")),
        "terminal_classification": as_str(terminal_summary.get("terminal_classification")),
        "closure": closure_payload(ledger_snapshot) if ledger_snapshot else None,
    }
    raw_events.append(
        RawTraceEvent(
            timestamp_epoch_seconds=_last_event_timestamp(progress_log, critical_events),
            event_kind="terminal_outcome",
            phase="terminal",
            iteration_index=as_int(snapshot.get("iterations")),
            actor="harness",
            status="completed",
            reason_code=terminal_snapshot.terminal_reason_code,
            refs_delta={},
            payload={k: v for k, v in terminal_payload.items() if v not in (None, "", {}, [])},
            source_origin={
                "kind": _SOURCE_KIND_TERMINAL,
                "ref": source_ref(primary=snapshot_ref, default=f"run:{run_id}"),
                "local_id": "terminal_summary",
                "sequence_index": len(progress_log) + len(critical_events) + 10000,
            },
        )
    )

    return build_canonical_trace(
        trace_id=trace_identifier,
        run_id=run_id,
        session_id=session_id,
        request_id=request_id,
        loop_family="transcript_edit",
        request_metadata=_request_metadata(run_entry=run_entry, snapshot=snapshot),
        start_context_summary=_start_context_summary(
            snapshot=snapshot,
            snapshot_ref=snapshot_ref,
            progress_count=len(progress_log),
            critical_count=len(critical_events),
        ),
        started_at_epoch_seconds=int(started_at_epoch_seconds),
        events=raw_events,
        terminal=terminal_snapshot,
        completeness_status="partial" if missing_components else "complete",
        missing_components=missing_components,
        normalization_warnings=warnings,
    )


def build_transcript_edit_trace_from_path(
    *,
    snapshot_path: str,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    payload = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object payload at {snapshot_path}")
    return build_transcript_edit_trace(
        run_snapshot=payload,
        snapshot_ref=snapshot_path,
        trace_id=trace_id,
    )


def _resolve_run_payload(run_snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(run_snapshot.get("snapshot"), dict):
        return run_snapshot, as_dict(run_snapshot.get("snapshot"))
    return {}, run_snapshot


def _extract_ledger_snapshot(
    *,
    progress_log: list[dict[str, Any]],
    critical_events: list[dict[str, Any]],
    terminal_summary: dict[str, Any],
) -> dict[str, Any]:
    terminal_ledger = as_dict(terminal_summary.get("decision_ledger"))
    if terminal_ledger:
        return terminal_ledger
    for event in reversed(progress_log):
        ledger = _ledger_from_event(event)
        if ledger:
            return ledger
    for event in reversed(critical_events):
        ledger = _ledger_from_event(event)
        if ledger:
            return ledger
    return {}


def _ledger_from_event(event: dict[str, Any]) -> dict[str, Any]:
    detail = as_dict(event.get("detail"))
    ledger = as_dict(detail.get("decision_ledger"))
    return ledger if ledger else {}


def _map_stream_events(
    *,
    events: list[dict[str, Any]],
    source_kind: str,
    source_ref_value: str,
    start_sequence: int,
) -> list[RawTraceEvent]:
    out: list[RawTraceEvent] = []
    for idx, event in enumerate(events):
        kind = event_kind(event=event)
        phase = as_str(event.get("phase"))
        payload = payload_for_stream_event(event=event)
        local_id = source_local_id(event=event, fallback=f"{phase or 'phase'}:{idx}")
        out.append(
            RawTraceEvent(
                timestamp_epoch_seconds=as_int(event.get("timestamp_epoch_seconds")),
                event_kind=kind,
                phase=phase,
                iteration_index=as_int(event.get("iteration")),
                actor=event_actor(event=event),
                status=event_status(event=event),
                reason_code=event_reason_code(event=event),
                refs_delta=refs_delta(event=event),
                payload=payload,
                source_origin={
                    "kind": source_kind,
                    "ref": source_ref_value,
                    "local_id": local_id,
                    "sequence_index": start_sequence + idx,
                },
            )
        )
    return out


def _map_blocker_registry_events(
    *,
    blocker_registry: dict[str, Any],
    source_ref_value: str,
    start_sequence: int,
) -> list[RawTraceEvent]:
    if not blocker_registry:
        return []
    out: list[RawTraceEvent] = []
    history = as_dict_list(blocker_registry.get("history"))
    for idx, row in enumerate(history):
        blocker_id = as_str(row.get("active_blocker_id"))
        out.append(
            RawTraceEvent(
                timestamp_epoch_seconds=as_int(row.get("timestamp_epoch_seconds")) or as_int(blocker_registry.get("updated_at")),
                event_kind="blocker_transition",
                phase="blocker_registry_history",
                iteration_index=as_int(row.get("iteration")),
                actor="harness",
                status="running",
                reason_code=as_str(row.get("reason")),
                refs_delta={},
                payload={
                    "blocker_id": blocker_id,
                    "prior_state": as_str(row.get("prior_state")),
                    "new_state": as_str(row.get("new_state")),
                    "action_attempted": as_str(row.get("action_attempted")),
                    "result": as_str(row.get("result")),
                    "source": "blocker_registry_history",
                },
                source_origin={
                    "kind": _SOURCE_KIND_BLOCKER_HISTORY,
                    "ref": source_ref_value,
                    "local_id": first_non_empty(blocker_id, f"history:{idx}"),
                    "sequence_index": start_sequence + idx,
                },
            )
        )
    rows = as_dict_list(blocker_registry.get("rows"))
    for idx, row in enumerate(rows):
        blocker_id = as_str(row.get("blocker_id"))
        if not blocker_id:
            continue
        out.append(
            RawTraceEvent(
                timestamp_epoch_seconds=as_int(row.get("updated_at")) or as_int(blocker_registry.get("updated_at")),
                event_kind="blocker_transition",
                phase="blocker_registry_row",
                iteration_index=None,
                actor="harness",
                status="running",
                reason_code=as_str(row.get("last_transition_reason")),
                refs_delta={},
                payload={
                    "blocker_id": blocker_id,
                    "decision_key": as_str(row.get("decision_key")),
                    "state": as_str(row.get("state")),
                    "feedback_status": as_str(row.get("feedback_status")),
                    "linked_prompt_id": as_str(row.get("linked_prompt_id")),
                    "linked_ticket_id": as_str(row.get("linked_ticket_id")),
                    "scope_status": as_str(row.get("scope_status")),
                    "source": "blocker_registry_row",
                },
                source_origin={
                    "kind": _SOURCE_KIND_BLOCKER_ROWS,
                    "ref": source_ref_value,
                    "local_id": blocker_id,
                    "sequence_index": start_sequence + len(history) + idx,
                },
            )
        )
    return out


def _map_hitl_state_events(
    *,
    runtime_hitl_state: dict[str, Any],
    source_ref_value: str,
    start_sequence: int,
) -> list[RawTraceEvent]:
    if not runtime_hitl_state:
        return []
    out: list[RawTraceEvent] = []
    lifecycle = as_dict_list(runtime_hitl_state.get("hitl_lifecycle_log"))
    for idx, row in enumerate(lifecycle):
        prompt_id = as_str(row.get("prompt_id"))
        ticket_id = as_str(row.get("ticket_id"))
        out.append(
            RawTraceEvent(
                timestamp_epoch_seconds=as_int(row.get("timestamp_epoch_seconds")),
                event_kind="hitl_escalation",
                phase=as_str(row.get("phase")) or "hitl_lifecycle",
                iteration_index=as_int(row.get("iteration")),
                actor="human",
                status="running",
                reason_code=as_str(row.get("reason")),
                refs_delta={},
                payload={
                    "prompt_id": prompt_id,
                    "ticket_id": ticket_id,
                    "decision_key": as_str(row.get("decision_key")),
                    "lifecycle_state": as_str(row.get("lifecycle_state")),
                    "source": "runtime_hitl_state",
                },
                source_origin={
                    "kind": _SOURCE_KIND_HITL_STATE,
                    "ref": source_ref_value,
                    "local_id": first_non_empty(prompt_id, ticket_id, f"hitl:{idx}"),
                    "sequence_index": start_sequence + idx,
                },
            )
        )
    return out


def _map_terminal_snapshot(
    *,
    status: str | None,
    reason_code: str | None,
    terminal_summary: dict[str, Any],
    ledger_snapshot: dict[str, Any],
) -> TerminalSnapshot:
    classification = as_str(terminal_summary.get("terminal_classification"))
    human_feedback_pending = bool(terminal_summary.get("human_feedback_pending"))
    classification_result = classify_transcript_edit_terminal(
        status=status,
        reason_code=reason_code,
        terminal_classification=classification,
        human_feedback_pending=human_feedback_pending,
    )

    metadata: dict[str, Any] = {
        "status": as_str(status),
        "terminal_classification": as_str(classification),
        "review_required": terminal_summary.get("review_required"),
    }
    closure = closure_payload(ledger_snapshot)
    if closure:
        metadata["closure"] = closure
    return TerminalSnapshot(
        terminal_class=classification_result.terminal_class,
        terminal_reason_code=classification_result.reason_code,
        success=True
        if classification_result.terminal_class == "completed"
        else False
        if classification_result.terminal_class in {"failed", "blocked", "exhausted"}
        else None,
        terminal_metadata={k: v for k, v in metadata.items() if v not in (None, "", {})},
    )


def _request_metadata(*, run_entry: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    request = as_dict(run_entry.get("request"))
    out = {
        "mode": as_str(request.get("mode")),
        "validation_mode": as_str(request.get("validation_mode")),
        "trigger": as_str(request.get("trigger")),
        "dossier_id": as_str(request.get("dossier_id")),
        "status": as_str(snapshot.get("status")),
    }
    return {k: v for k, v in out.items() if v not in (None, "")}


def _start_context_summary(
    *,
    snapshot: dict[str, Any],
    snapshot_ref: str | None,
    progress_count: int,
    critical_count: int,
) -> dict[str, Any]:
    out = {
        "run_artifact_ref": as_str(snapshot.get("run_artifact_ref")),
        "snapshot_ref": snapshot_ref,
        "progress_events_count": progress_count,
        "critical_events_count": critical_count,
        "waiting_feedback": snapshot.get("waiting_feedback"),
        "resumable": snapshot.get("resumable"),
    }
    return {k: v for k, v in out.items() if v not in (None, "", {})}


def _synth_iteration_events(
    *,
    progress_log: list[dict[str, Any]],
    source_ref_value: str,
    start_sequence: int,
) -> list[RawTraceEvent]:
    out: list[RawTraceEvent] = []
    seen: set[int] = set()
    for event in progress_log:
        iteration = as_int(event.get("iteration"))
        if iteration is None or iteration in seen:
            continue
        seen.add(iteration)
        timestamp = as_int(event.get("timestamp_epoch_seconds"))
        out.append(
            RawTraceEvent(
                timestamp_epoch_seconds=timestamp,
                event_kind="iteration",
                phase="iteration_checkpoint",
                iteration_index=iteration,
                actor="harness",
                status="running",
                reason_code=None,
                refs_delta={},
                payload={"source": "progress_iteration_checkpoint", "synthesized": True},
                source_origin={
                    "kind": _SOURCE_KIND_PROGRESS,
                    "ref": source_ref_value,
                    "local_id": f"iteration:{iteration}",
                    "sequence_index": start_sequence + iteration,
                },
            )
        )
    return out


def _first_event_timestamp(progress_log: list[dict[str, Any]], critical_events: list[dict[str, Any]]) -> int | None:
    for event in progress_log:
        value = as_int(event.get("timestamp_epoch_seconds"))
        if value is not None:
            return value
    for event in critical_events:
        value = as_int(event.get("timestamp_epoch_seconds"))
        if value is not None:
            return value
    return None


def _last_event_timestamp(progress_log: list[dict[str, Any]], critical_events: list[dict[str, Any]]) -> int | None:
    for event in reversed(progress_log):
        value = as_int(event.get("timestamp_epoch_seconds"))
        if value is not None:
            return value
    for event in reversed(critical_events):
        value = as_int(event.get("timestamp_epoch_seconds"))
        if value is not None:
            return value
    return None


def _default_trace_id(
    *,
    run_id: str,
    snapshot_ref: str | None,
    progress_log: list[dict[str, Any]],
    critical_events: list[dict[str, Any]],
) -> str:
    seed = "|".join(
        [
            run_id,
            snapshot_ref or "",
            str(len(progress_log)),
            str(len(critical_events)),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"trace:transcript_edit:{run_id}:{digest}"
