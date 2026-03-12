from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..builder import build_canonical_trace
from ..schema import CanonicalTraceRecord, RawTraceEvent, TerminalSnapshot
from .controller_kernel_helpers import (
    as_dict,
    as_dict_list,
    as_int,
    as_str,
    as_str_list,
    bounded_text,
    extract_run_id_from_session,
    first_non_empty,
    map_terminal_class,
    source_ref,
)

_MAX_DETAIL_CHARS = 180
_MAX_DELTA_CHARS = 240
_MAX_PROPOSAL_SOURCE_CHARS = 64

_TRANSCRIPT_SOURCE_KIND = "controller_transcript"
_KERNEL_STEP_SOURCE_KIND = "kernel_step_record"
_TERMINAL_SOURCE_KIND = "controller_terminal"

_TRANSCRIPT_EVENT_MAP: dict[str, tuple[str, str, str]] = {
    "run_header": ("request_start", "controller", "started"),
    "start_refused": ("request_start", "controller", "refused"),
    "agent_proposed_step": ("model_proposal", "model", "completed"),
    "controller_parse_fail_resync": ("model_proposal", "controller", "failed"),
    "controller_refusal": ("model_proposal", "controller", "refused"),
    "kernel_step_result": ("tool_execution", "kernel", "running"),
    "retrieval_degradation": ("retrieval_evidence", "controller", "completed"),
    "bootstrap_span_seeds_materialized": ("iteration", "controller", "running"),
    "transcript_truncated": ("iteration", "harness", "failed"),
}


def build_controller_kernel_trace(
    *,
    controller_transcript: dict[str, Any],
    run_artifact: dict[str, Any],
    transcript_ref: str | None = None,
    run_artifact_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    transcript_events = as_dict_list(controller_transcript.get("events"))
    run_steps = as_dict_list(run_artifact.get("steps"))
    run_header = _find_run_header(transcript_events)

    run_id = first_non_empty(
        run_artifact.get("run_id"),
        extract_run_id_from_session(as_str(run_artifact.get("session_id"))),
        extract_run_id_from_session(as_str(run_header.get("session_id"))),
        "unknown_run",
    )
    request_id = first_non_empty(run_artifact.get("request_id"), run_header.get("request_id"), "unknown_request")
    session_id = first_non_empty(run_artifact.get("session_id"), run_header.get("session_id"), None)
    started_at = as_int(run_artifact.get("created_at_epoch_seconds")) or _first_event_timestamp(transcript_events) or 0
    canonical_trace_id = trace_id or _default_trace_id(
        run_id=run_id,
        transcript_ref=transcript_ref,
        run_artifact_ref=run_artifact_ref,
        transcript_events=transcript_events,
        run_steps=run_steps,
    )

    missing_components: list[str] = []
    warnings: list[str] = []
    if not transcript_events:
        missing_components.append("controller_transcript_events")
        warnings.append("controller_transcript_missing_events")
    if not run_steps:
        missing_components.append("kernel_run_steps")
        warnings.append("kernel_run_artifact_missing_steps")
    if _has_transcript_truncation(transcript_events):
        missing_components.append("controller_transcript_history")
        warnings.append("controller_transcript_truncated")
    if not run_header:
        warnings.append("run_header_missing")

    raw_events, adapter_warnings = _map_transcript_events(
        transcript_events=transcript_events,
        run_steps=run_steps,
        transcript_ref=transcript_ref,
        run_artifact_ref=run_artifact_ref,
    )
    warnings.extend(adapter_warnings)
    if "kernel_step_alignment_missing" in adapter_warnings:
        missing_components.append("kernel_step_alignment")
    terminal_source, terminal_reason = _extract_terminal(transcript_events, run_artifact)
    if terminal_source is None:
        missing_components.append("controller_terminal")
        warnings.append("controller_terminal_missing_synthesized_failed")
        terminal_source = {
            "terminal_outcome": "FAILED",
            "stop_reason": "internal_error",
            "success": False,
            "reason_code": "controller_terminal_missing",
        }
        terminal_reason = "controller_terminal_missing"

    terminal_snapshot = _map_terminal_snapshot(terminal_source)
    raw_events.append(
        RawTraceEvent(
            timestamp_epoch_seconds=_last_event_timestamp(transcript_events),
            event_kind="terminal_outcome",
            phase="terminal",
            iteration_index=None,
            actor="harness",
            status="completed",
            reason_code=terminal_reason,
            refs_delta={},
            payload={
                "terminal_outcome": as_str(terminal_source.get("terminal_outcome")),
                "stop_reason": as_str(terminal_source.get("stop_reason")),
                "success": terminal_source.get("success"),
            },
            source_origin={
                "kind": _TERMINAL_SOURCE_KIND,
                "ref": source_ref(
                    primary=transcript_ref,
                    fallback=run_artifact_ref,
                    default=f"run:{run_id}",
                ),
                "local_id": terminal_reason,
                "sequence_index": len(transcript_events),
            },
        )
    )

    return build_canonical_trace(
        trace_id=canonical_trace_id,
        run_id=run_id,
        session_id=session_id,
        request_id=request_id,
        loop_family="controller_kernel",
        request_metadata=_build_request_metadata(run_header=run_header, run_artifact=run_artifact),
        start_context_summary=_build_start_context_summary(
            run_header=run_header,
            run_artifact=run_artifact,
            transcript_ref=transcript_ref,
            run_artifact_ref=run_artifact_ref,
        ),
        started_at_epoch_seconds=int(started_at),
        events=raw_events,
        terminal=terminal_snapshot,
        completeness_status="partial" if missing_components else "complete",
        missing_components=missing_components,
        normalization_warnings=warnings,
    )


def build_controller_kernel_trace_from_paths(
    *,
    controller_transcript_path: str,
    run_artifact_path: str,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    return build_controller_kernel_trace(
        controller_transcript=_load_json_dict(controller_transcript_path),
        run_artifact=_load_json_dict(run_artifact_path),
        transcript_ref=controller_transcript_path,
        run_artifact_ref=run_artifact_path,
        trace_id=trace_id,
    )


def _load_json_dict(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object payload at {path}")
    return payload


def _map_transcript_events(
    *,
    transcript_events: list[dict[str, Any]],
    run_steps: list[dict[str, Any]],
    transcript_ref: str | None,
    run_artifact_ref: str | None,
) -> tuple[list[RawTraceEvent], list[str]]:
    out: list[RawTraceEvent] = []
    warnings: list[str] = []
    step_cursor = 0
    for idx, event in enumerate(transcript_events):
        event_type = as_str(event.get("event_type")) or "unknown_event"
        detail = as_str(event.get("detail"))
        payload = as_dict(event.get("payload"))
        timestamp = as_int(event.get("timestamp_epoch_seconds"))
        event_kind, actor, status = _map_transcript_event_shape(event_type=event_type, detail=detail)
        reason_code = _reason_code_from_transcript_event(event_type=event_type, detail=detail, payload=payload)
        refs_delta = _refs_delta_from_payload(payload=payload)
        source_kind = _TRANSCRIPT_SOURCE_KIND
        source_ref_value = source_ref(
            primary=transcript_ref,
            fallback=run_artifact_ref,
            default="inline:controller_transcript",
        )
        local_id = f"{event_type}:{idx}"
        event_payload = _event_payload_snapshot(event_type=event_type, detail=detail, payload=payload)
        if event_type == "kernel_step_result":
            step, step_idx = _aligned_run_step(
                run_steps=run_steps,
                start_index=step_cursor,
                transcript_action=as_str(payload.get("action_type")),
            )
            if step:
                step_cursor = step_idx + 1
                step_id = as_str(step.get("step_id"))
                if step_id:
                    source_kind = _KERNEL_STEP_SOURCE_KIND
                    source_ref_value = source_ref(
                        primary=run_artifact_ref,
                        fallback=transcript_ref,
                        default="inline:run_artifact",
                    )
                    local_id = step_id
                    event_payload["step_id"] = step_id
                    action = as_str(step.get("action"))
                    if action:
                        event_payload["run_step_action"] = action
                    reason_codes = as_str_list(step.get("reason_codes"))
                    if reason_codes:
                        event_payload["run_step_reason_codes"] = reason_codes[:4]
                    refs_delta = _merge_refs(
                        refs_delta,
                        _refs_delta_from_step_outputs(step.get("outputs")),
                    )
            else:
                _push_unique_warning(warnings, "kernel_step_alignment_missing")
        out.append(
            RawTraceEvent(
                timestamp_epoch_seconds=timestamp,
                event_kind=event_kind,
                phase=_phase_from_event_type(event_type),
                iteration_index=as_int(payload.get("iteration")),
                actor=actor,
                status=status,
                reason_code=reason_code,
                refs_delta=refs_delta,
                payload=event_payload,
                source_origin={
                    "kind": source_kind,
                    "ref": source_ref_value,
                    "local_id": local_id,
                    "sequence_index": step_idx if source_kind == _KERNEL_STEP_SOURCE_KIND else idx,
                },
            )
        )
    return out, warnings


def _map_transcript_event_shape(*, event_type: str, detail: str | None) -> tuple[str, str, str]:
    event_kind, actor, status = _TRANSCRIPT_EVENT_MAP.get(event_type, ("iteration", "harness", "unknown"))
    if event_type != "kernel_step_result":
        return event_kind, actor, status
    normalized = (detail or "").strip().lower()
    if normalized in {"executed", "deduped"}:
        return event_kind, actor, "completed"
    if normalized == "refused":
        return event_kind, actor, "refused"
    return event_kind, actor, "unknown"


def _reason_code_from_transcript_event(
    *,
    event_type: str,
    detail: str | None,
    payload: dict[str, Any],
) -> str | None:
    if event_type in {"controller_refusal", "start_refused", "kernel_step_result"}:
        refusal = as_dict(payload.get("refusal"))
        refusal_reason = as_str(refusal.get("reason_code"))
        if refusal_reason:
            return refusal_reason
    if event_type == "kernel_step_result":
        failure = as_dict(payload.get("dashboard_failure_classification"))
        return as_str(failure.get("reason_code")) or detail
    if event_type == "retrieval_degradation":
        return as_str(payload.get("reason_code")) or detail
    return detail


def _refs_delta_from_payload(*, payload: dict[str, Any]) -> dict[str, Any]:
    refs = as_dict(payload.get("latest_refs"))
    return refs if refs else {}


def _refs_delta_from_step_outputs(outputs: Any) -> dict[str, Any]:
    data = as_dict(outputs)
    refs: dict[str, Any] = {}
    for key, value in data.items():
        if not key.endswith("_artifact_ref"):
            continue
        if isinstance(value, dict):
            artifact_path = as_str(value.get("artifact_path"))
            if artifact_path:
                refs[key] = artifact_path
        elif isinstance(value, str) and value:
            refs[key] = value
    return refs


def _event_payload_snapshot(
    *,
    event_type: str,
    detail: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    out: dict[str, Any] = {"event_type": event_type}
    detail_excerpt = bounded_text(detail, max_chars=_MAX_DETAIL_CHARS)
    if detail_excerpt:
        out["detail"] = detail_excerpt
    action_type = as_str(payload.get("action_type"))
    if action_type:
        out["action_type"] = action_type
    proposal_source = bounded_text(payload.get("proposal_source"), max_chars=_MAX_PROPOSAL_SOURCE_CHARS)
    if proposal_source:
        out["proposal_source"] = proposal_source
    idempotency_key = as_str(payload.get("idempotency_key"))
    if idempotency_key:
        out["idempotency_key"] = idempotency_key
    display_delta = bounded_text(payload.get("display_delta"), max_chars=_MAX_DELTA_CHARS)
    if display_delta:
        out["display_delta_excerpt"] = display_delta
    fallback = bounded_text(payload.get("fallback"), max_chars=_MAX_DETAIL_CHARS)
    if fallback:
        out["fallback_excerpt"] = fallback

    terminal = as_dict(payload.get("terminal"))
    if terminal:
        out["terminal"] = {
            "terminal_outcome": as_str(terminal.get("terminal_outcome")),
            "stop_reason": as_str(terminal.get("stop_reason")),
            "reason_code": as_str(terminal.get("reason_code")),
            "success": terminal.get("success"),
        }
    refusal = as_dict(payload.get("refusal"))
    if refusal:
        out["refusal"] = {
            "reason_code": as_str(refusal.get("reason_code")),
            "retryable": refusal.get("retryable"),
            "blocked_by_budget": refusal.get("blocked_by_budget"),
            "blocked_by_invariant": refusal.get("blocked_by_invariant"),
        }
    return out


def _phase_from_event_type(event_type: str) -> str:
    if event_type in {"run_header", "start_refused", "bootstrap_span_seeds_materialized"}:
        return "bootstrap"
    if event_type in {"agent_proposed_step", "controller_parse_fail_resync"}:
        return "proposal"
    if event_type in {"controller_refusal", "kernel_step_result"}:
        return "execution"
    if event_type == "retrieval_degradation":
        return "retrieval"
    if event_type == "transcript_truncated":
        return "observability"
    return "unknown"


def _extract_terminal(
    transcript_events: list[dict[str, Any]],
    run_artifact: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    for event in reversed(transcript_events):
        payload = as_dict(event.get("payload"))
        terminal = as_dict(payload.get("terminal"))
        if terminal:
            return terminal, as_str(terminal.get("reason_code")) or as_str(event.get("detail"))
    ledger = as_dict(run_artifact.get("idempotency_ledger"))
    for entry in reversed(list(ledger.values())):
        data = as_dict(entry)
        terminal = as_dict(data.get("terminal"))
        if terminal:
            return terminal, as_str(terminal.get("reason_code"))
    return None, None


def _map_terminal_snapshot(terminal: dict[str, Any]) -> TerminalSnapshot:
    stop_reason = as_str(terminal.get("stop_reason"))
    terminal_outcome = as_str(terminal.get("terminal_outcome"))
    success = terminal.get("success")
    return TerminalSnapshot(
        terminal_class=map_terminal_class(
            stop_reason=stop_reason,
            terminal_outcome=terminal_outcome,
            success=success,
        ),
        terminal_reason_code=as_str(terminal.get("reason_code")),
        success=bool(success) if isinstance(success, bool) else None,
        terminal_metadata={
            "stop_reason": stop_reason,
            "terminal_outcome": terminal_outcome,
        },
    )


def _build_request_metadata(*, run_header: dict[str, Any], run_artifact: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "request_id": first_non_empty(run_artifact.get("request_id"), run_header.get("request_id")),
        "dossier_id": as_str(run_header.get("dossier_id")),
        "source_entry_ref": as_str(run_header.get("source_entry_ref")),
        "model": as_str(run_header.get("model")),
    }
    tool_menu = run_header.get("tool_menu")
    if isinstance(tool_menu, list):
        out["tool_menu_size"] = len(tool_menu)
    return {k: v for k, v in out.items() if v not in (None, "")}


def _build_start_context_summary(
    *,
    run_header: dict[str, Any],
    run_artifact: dict[str, Any],
    transcript_ref: str | None,
    run_artifact_ref: str | None,
) -> dict[str, Any]:
    bootstrap_context = as_dict(run_header.get("bootstrap_context"))
    budget_keys = sorted(as_dict(run_artifact.get("session_budgets")).keys())[:8]
    out: dict[str, Any] = {
        "bootstrap_context_keys": sorted(bootstrap_context.keys())[:16],
        "initial_run_artifact_ref": first_non_empty(run_header.get("run_artifact_ref"), run_artifact_ref),
        "transcript_ref": transcript_ref,
        "session_budget_keys": budget_keys,
        "requires_global_placement": run_artifact.get("requires_global_placement"),
        "render_required": run_artifact.get("render_required"),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


def _find_run_header(transcript_events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in transcript_events:
        if as_str(event.get("event_type")) != "run_header":
            continue
        payload = event.get("payload")
        if isinstance(payload, dict):
            return payload
    return {}


def _has_transcript_truncation(transcript_events: list[dict[str, Any]]) -> bool:
    for event in transcript_events:
        if as_str(event.get("event_type")) == "transcript_truncated":
            return True
    return False


def _first_event_timestamp(transcript_events: list[dict[str, Any]]) -> int | None:
    for event in transcript_events:
        value = as_int(event.get("timestamp_epoch_seconds"))
        if value is not None:
            return value
    return None


def _last_event_timestamp(transcript_events: list[dict[str, Any]]) -> int | None:
    for event in reversed(transcript_events):
        value = as_int(event.get("timestamp_epoch_seconds"))
        if value is not None:
            return value
    return None


def _default_trace_id(
    *,
    run_id: str,
    transcript_ref: str | None,
    run_artifact_ref: str | None,
    transcript_events: list[dict[str, Any]],
    run_steps: list[dict[str, Any]],
) -> str:
    seed = "|".join(
        [
            run_id,
            transcript_ref or "",
            run_artifact_ref or "",
            str(len(transcript_events)),
            str(len(run_steps)),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"trace:controller_kernel:{run_id}:{digest}"


def _merge_refs(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    if not secondary:
        return primary
    merged = dict(primary)
    for key, value in secondary.items():
        if key not in merged:
            merged[key] = value
    return merged


def _aligned_run_step(
    *,
    run_steps: list[dict[str, Any]],
    start_index: int,
    transcript_action: str | None,
) -> tuple[dict[str, Any], int]:
    if start_index >= len(run_steps):
        return {}, -1
    if not transcript_action:
        return {}, -1
    for idx in range(start_index, len(run_steps)):
        step = run_steps[idx]
        if as_str(step.get("action")) == transcript_action:
            return step, idx
    return {}, -1


def _push_unique_warning(warnings: list[str], warning: str) -> None:
    if warning in warnings:
        return
    warnings.append(warning)
