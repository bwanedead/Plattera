"""Controller loop split module (Pass 6)."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root, dossiers_feature_graphs_artifacts_root
from feature_graph.operations import get_supported_operations, get_unsupported_operations

from agent_kernel.models import (
    ActionType,
    KernelRefusal,
    KernelSessionStartRequest,
    KernelSessionStartResult,
    KernelStepRequest,
    KernelStepResult,
    StepExecutionState,
    StopReason,
    TerminalOutcome,
    TerminalOutcomeKind,
)
from agent_kernel.session import KernelSessionManager

from .contracts import (
    DeclareDoneJustification,
    KernelStepProposal,
    action_tool_specs_for_menu,
    action_how_to_guide,
    coerce_action_type,
    tool_cheatsheet_entries,
    validate_action_args,
)
from .prompting import (
    build_developer_message,
    build_refusal_repair_user_message,
    build_repair_user_message,
    build_user_message,
)
from .retrieval_intents import classify_retrieval_degradation, map_retrieval_intent_to_inputs
from .tool_specs import ToolSpec
from .bootstrap import load_transcript_span_seeds_for_mapping, materialize_seed_spans_from_text

_MAX_CONTROLLER_INPUT_BYTES = 4096
_MAX_EVENTS = 200
_MAX_EVENT_CHARS = 2000
_MAX_TOTAL_BYTES = 262144
_MAX_ERROR_CHARS = 1000
_MAX_TRACE_ITEMS = 8
_MAX_PLAN_BULLETS = 8
_MAX_GAP_KINDS = 8
_MAX_REASON_CODES = 8
_MAX_REFUSAL_STREAK = 3
_RUN_SUMMARY_EVERY_EXECUTED_STEPS = 5
_MAX_HINT_FILE_BYTES = 65536
_MAX_HINT_READ_BYTES = 32768
_RUN_SUMMARY_LOG_MAX_BYTES = 24576
_RUN_SUMMARY_LOG_MAX_ENTRIES = 40
_MAX_DISPLAY_DELTA_CHARS = 220

logger = logging.getLogger(__name__)

from .controller_guardrails import _latest_refs_summary, _read_str

def _bounded_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 14]}...[truncated]"


def _bound_payload(value: object, *, max_items: int = 24) -> object:
    if isinstance(value, str):
        return _bounded_text(value, _MAX_EVENT_CHARS)
    if isinstance(value, list):
        trimmed = value[:max_items]
        return [_bound_payload(v, max_items=max_items) for v in trimmed]
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for idx, (key, val) in enumerate(value.items()):
            if idx >= max_items:
                break
            out[str(key)] = _bound_payload(val, max_items=max_items)
        return out
    return value


def _maybe_create_iteration_digest(
    *,
    digest_client: IterationDigestClient | None,
    request_id: str,
    session_id: str,
    iteration: int,
    context_packet: dict[str, object],
    phase_hint: str,
    proposal: KernelStepProposal,
    outcome_kind: str,
    outcome_payload: dict[str, object],
    recent_digest_memory: list[dict[str, object]],
    executed_steps: int = 0,
) -> list[dict[str, object]]:
    from .controller_transcript import _log_controller_event

    if not _should_emit_iteration_digest(outcome_kind=outcome_kind, executed_steps=executed_steps):
        return recent_digest_memory
    del digest_client, request_id, session_id  # disabled for single-pipe mode; deterministic fallback only
    run_summary_entry = _build_run_summary_entry(
        iteration=iteration,
        phase_hint=phase_hint,
        proposal=proposal,
        outcome_kind=outcome_kind,
        outcome_payload=outcome_payload,
    )
    updated = list(recent_digest_memory)
    deed_span_index_ref = None
    deed_span_catalog_excerpt = None
    progress = context_packet.get("progress")
    if isinstance(progress, dict):
        latest_refs = progress.get("latest_refs")
        if isinstance(latest_refs, dict):
            deed_span_index_ref = latest_refs.get("deed_span_index_ref")
    step_record = outcome_payload.get("step_record")
    if isinstance(step_record, dict):
        outputs_inline = step_record.get("outputs_inline")
        if isinstance(outputs_inline, dict):
            if deed_span_index_ref is None:
                raw_ref = outputs_inline.get("deed_span_index_ref")
                if isinstance(raw_ref, dict):
                    deed_span_index_ref = raw_ref.get("artifact_path")
            if isinstance(outputs_inline.get("span_catalog_excerpt"), list):
                deed_span_catalog_excerpt = outputs_inline.get("span_catalog_excerpt")
    if isinstance(outcome_payload.get("latest_refs"), dict):
        deed_span_index_ref = outcome_payload["latest_refs"].get("deed_span_index_ref") or deed_span_index_ref
    updated.append(
        {
            "iter": iteration,
            "digest_ref": None,
            "digest_excerpt": _run_summary_entry_excerpt(run_summary_entry),
            "deed_span_index_ref": deed_span_index_ref,
            "deed_span_catalog_excerpt": deed_span_catalog_excerpt,
            "run_summary_entry": run_summary_entry,
        }
    )
    bounded = _bound_run_summary_memory(updated)
    _log_controller_event(
        "iteration_summary_appended",
        {
            "iteration": iteration,
            "source": run_summary_entry.get("source"),
            "action": run_summary_entry.get("action"),
            "outcome_kind": outcome_kind,
            "run_summary_log_entries": len([e for e in bounded if isinstance(e.get("run_summary_entry"), dict)]),
        },
    )
    return bounded


def _should_emit_iteration_digest(*, outcome_kind: str, executed_steps: int) -> bool:
    if executed_steps == 0:
        return True
    if outcome_kind in {"controller_refusal", "kernel_refusal"}:
        return True
    if outcome_kind == "executed" and executed_steps % 3 == 0:
        return True
    return False


def _build_run_summary_entry(
    *,
    iteration: int,
    phase_hint: str,
    proposal: KernelStepProposal,
    outcome_kind: str,
    outcome_payload: dict[str, object],
) -> dict[str, object]:
    if proposal.iteration_summary is not None:
        summary = _normalize_iteration_summary_payload(proposal.iteration_summary)
        if summary:
            return {"iter": iteration, "source": "agent", **summary}
    return {
        "iter": iteration,
        "source": "fallback",
        **_fallback_iteration_summary(
            phase_hint=phase_hint,
            proposal=proposal,
            outcome_kind=outcome_kind,
            outcome_payload=outcome_payload,
        ),
    }


def _normalize_iteration_summary_payload(summary: object) -> dict[str, object] | None:
    if summary is None:
        return None
    if isinstance(summary, dict):
        return _normalize_docket_dict(summary)
    if isinstance(summary, str):
        out = {
            "actual_observation": _bounded_docket_text(summary, 200),
            "confidence": "low",
            "state_delta": {"summary_payload_type": "string"},
        }
        return _finalize_docket_summary(out)
    if isinstance(summary, list):
        items: list[str] = []
        for item in summary[:4]:
            items.append(_bounded_docket_text(item if isinstance(item, str) else repr(item), 120))
        out = {
            "actual_observation": "iteration_summary_non_object_received",
            "open_issues": items[:4],
            "confidence": "low",
            "state_delta": {"summary_payload_type": "list"},
        }
        return _finalize_docket_summary(out)
    out = {
        "actual_observation": "iteration_summary_non_object_received",
        "do_not_repeat": _bounded_docket_text(repr(summary), 160),
        "confidence": "low",
        "state_delta": {"summary_payload_type": type(summary).__name__},
    }
    return _finalize_docket_summary(out)


def _normalize_docket_dict(raw: Mapping[str, object]) -> dict[str, object] | None:
    out: dict[str, object] = {}
    for key in (
        "action",
        "intent",
        "expected_observation",
        "actual_observation",
        "do_not_repeat",
    ):
        value = raw.get(key)
        if value is None:
            continue
        text = _bounded_docket_text(value if isinstance(value, str) else repr(value), 200 if key != "action" else 120)
        if text:
            out[key] = text

    open_issues = raw.get("open_issues")
    if isinstance(open_issues, list):
        issues: list[str] = []
        for item in open_issues[:6]:
            issues.append(_bounded_docket_text(item if isinstance(item, str) else repr(item), 120))
        if issues:
            out["open_issues"] = issues
    elif isinstance(open_issues, str):
        issue = _bounded_docket_text(open_issues, 120)
        if issue:
            out["open_issues"] = [issue]

    confidence = raw.get("confidence")
    if isinstance(confidence, (int, float)):
        out["confidence"] = max(0.0, min(1.0, float(confidence)))
    elif isinstance(confidence, str):
        bounded_conf = _bounded_docket_text(confidence, 40)
        if bounded_conf:
            out["confidence"] = bounded_conf

    next_move = raw.get("next_move")
    if isinstance(next_move, dict):
        next_action = next_move.get("action_type")
        next_why = next_move.get("why")
        next_out: dict[str, object] = {}
        if isinstance(next_action, str) and next_action.strip():
            next_out["action_type"] = _bounded_docket_text(next_action, 64)
        if next_why is not None:
            next_out["why"] = _bounded_docket_text(next_why if isinstance(next_why, str) else repr(next_why), 160)
        if next_out:
            out["next_move"] = next_out

    state_delta = raw.get("state_delta")
    if isinstance(state_delta, dict):
        out["state_delta"] = _normalize_docket_state_delta(state_delta)

    if not out:
        out = {
            "actual_observation": "iteration_summary_empty_or_unusable",
            "confidence": "low",
            "state_delta": {"summary_payload_type": "object"},
        }
    return _finalize_docket_summary(out)


def _normalize_docket_state_delta(raw: Mapping[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    new_refs = raw.get("new_refs")
    if isinstance(new_refs, list):
        refs: list[str] = []
        for item in new_refs[:6]:
            refs.append(_bounded_docket_text(item if isinstance(item, str) else repr(item), 80))
        if refs:
            out["new_refs"] = refs
    gap_change = raw.get("gap_change")
    if gap_change is not None:
        out["gap_change"] = _bounded_docket_text(gap_change if isinstance(gap_change, str) else repr(gap_change), 120)
    phase_hint = raw.get("phase_hint")
    if phase_hint is not None:
        out["phase_hint"] = _bounded_docket_text(phase_hint if isinstance(phase_hint, str) else repr(phase_hint), 64)
    arg_keys = raw.get("arg_keys")
    if isinstance(arg_keys, list):
        keys: list[str] = []
        for item in arg_keys[:8]:
            keys.append(_bounded_docket_text(item if isinstance(item, str) else repr(item), 48))
        if keys:
            out["arg_keys"] = keys
    if not out:
        out = {"summary_delta": "none"}
    return _bound_payload(out, max_items=8)


def _finalize_docket_summary(out: dict[str, object]) -> dict[str, object] | None:
    encoded = json.dumps(out, ensure_ascii=True).encode("utf-8")
    if len(encoded) > 2048:
        return {"truncated": True}
    return out


def _bounded_docket_text(text: str, max_chars: int) -> str:
    bounded = _bounded_text(text, max_chars)
    if _looks_like_global_recap(bounded):
        bounded = _bounded_text(bounded, min(max_chars, 120))
    if "deed text" in bounded.lower():
        bounded = _bounded_text(bounded, min(max_chars, 120))
    return bounded


def _fallback_iteration_summary(
    *,
    phase_hint: str,
    proposal: KernelStepProposal,
    outcome_kind: str,
    outcome_payload: dict[str, object],
) -> dict[str, object]:
    reason_code = outcome_payload.get("reason_code")
    missing_inputs = outcome_payload.get("missing_inputs")
    latest_refs = outcome_payload.get("latest_refs") if isinstance(outcome_payload.get("latest_refs"), dict) else {}
    new_refs = [k for k, v in latest_refs.items() if isinstance(v, str) and v][:4]
    actual_observation = _fallback_actual_observation(outcome_kind=outcome_kind, reason_code=reason_code)
    entry: dict[str, object] = {
        "action": _bounded_text(f"propose:{proposal.action_type}; observed_last:{actual_observation}", 120),
        "intent": _bounded_text(proposal.why, 160),
        "actual_observation": actual_observation,
        "expected_observation": _fallback_expected_observation(proposal=proposal, outcome_kind=outcome_kind),
        "state_delta": {"phase_hint": phase_hint, "arg_keys": sorted(proposal.args.keys())},
        "open_issues": [],
        "next_move": {"action_type": proposal.action_type, "why": "retry with corrected args or use a different tool based on latest state"},
        "confidence": "low",
    }
    if outcome_kind in {"controller_refusal", "kernel_refusal"}:
        if isinstance(missing_inputs, list) and missing_inputs:
            entry["open_issues"] = [str(v)[:160] for v in missing_inputs[:3]]
            entry["expected_observation"] = _bounded_text(
                f"if corrected {proposal.action_type} executes, next state should clear refusal:{reason_code or 'unknown'}",
                200,
            )
        entry["do_not_repeat"] = "Do not resend identical args after the same refusal without adding required fields."
    elif outcome_kind == "executed":
        entry["actual_observation"] = "latest kernel step executed"
        entry["state_delta"] = {"phase_hint": phase_hint, "new_refs": new_refs, "gap_change": "unknown_or_unchanged"}
        entry["confidence"] = "med"
    else:
        entry["actual_observation"] = _bounded_text(str(outcome_kind), 160)
    finalized = _normalize_docket_dict(entry)
    return finalized or {"actual_observation": "fallback_summary_unavailable", "confidence": "low"}


def _fallback_actual_observation(*, outcome_kind: str, reason_code: object) -> str:
    if outcome_kind in {"controller_refusal", "kernel_refusal"}:
        return _bounded_text(f"refused({reason_code or 'unknown'})", 160)
    if outcome_kind == "executed":
        return "executed"
    if outcome_kind == "parse_failed":
        return "parse_failed"
    return _bounded_text(str(outcome_kind), 160)


def _fallback_expected_observation(*, proposal: KernelStepProposal, outcome_kind: str) -> str:
    if outcome_kind in {"controller_refusal", "kernel_refusal"}:
        return _bounded_text(f"next iteration should observe {proposal.action_type} execution if args are corrected", 200)
    if outcome_kind == "executed":
        return _bounded_text(
            f"next iteration should observe updated refs/gaps after {proposal.action_type}",
            200,
        )
    return _bounded_text(f"next iteration should observe a clearer outcome for {proposal.action_type}", 200)


def _run_summary_entry_excerpt(entry: dict[str, object]) -> str:
    return _bounded_text(
        f"iter={entry.get('iter')}; source={entry.get('source')}; action={entry.get('action')}; obs={entry.get('actual_observation')}",
        220,
    )


def _bound_run_summary_memory(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    bounded = list(entries[-_RUN_SUMMARY_LOG_MAX_ENTRIES:])
    while bounded and _run_summary_memory_bytes(bounded) > _RUN_SUMMARY_LOG_MAX_BYTES:
        bounded.pop(0)
    if _run_summary_memory_bytes(bounded) <= _RUN_SUMMARY_LOG_MAX_BYTES:
        return bounded
    # Aggressive truncation fallback
    for item in bounded:
        summary = item.get("run_summary_entry")
        if isinstance(summary, dict):
            for key, value in list(summary.items()):
                if isinstance(value, str):
                    summary[key] = _bounded_text(value, 80)
                elif isinstance(value, list):
                    summary[key] = [str(v)[:80] for v in value[:2]]
                elif isinstance(value, dict):
                    summary[key] = _bound_payload(value, max_items=4)
    while bounded and _run_summary_memory_bytes(bounded) > _RUN_SUMMARY_LOG_MAX_BYTES:
        bounded.pop(0)
    return bounded


def _run_summary_memory_bytes(entries: list[dict[str, object]]) -> int:
    payload = [e.get("run_summary_entry") for e in entries if isinstance(e.get("run_summary_entry"), dict)]
    return len(json.dumps(payload, ensure_ascii=True).encode("utf-8"))


def _looks_like_global_recap(text: str) -> bool:
    lower = text.lower()
    return len(text) > 140 and any(token in lower for token in ("so far", "previously", "earlier steps", "history"))


def _persist_run_summary(
    *,
    request_id: str,
    session_id: str,
    phase_hint: str,
    dashboard: dict[str, object],
    last_refusal: dict[str, object] | None,
    transcript: list[dict[str, object]],
) -> tuple[str, str]:
    from .controller_context import _extract_recent_trace

    root = agent_kernel_artifacts_root() / "controller_summaries" / request_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{session_id.replace(':', '_')}_{uuid4().hex[:8]}.json"
    summary = {
        "phase_hint": phase_hint,
        "latest_refs": _latest_refs_summary(dashboard),
        "claimability": dashboard.get("claimability"),
        "failure_classification": dashboard.get("failure_classification"),
        "last_refusal": last_refusal,
        "recent_trace": _extract_recent_trace(transcript),
        "created_at_epoch_seconds": int(time()),
    }
    fd, tmp_path = tempfile.mkstemp(prefix="controller_summary_", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            with path.open("w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    excerpt = _bounded_text(
        f"phase={phase_hint}; refs={','.join(summary['latest_refs'].keys())}; "
        f"claimable={bool((summary.get('claimability') or {}).get('claimable_ready'))}",
        240,
    )
    return str(path), excerpt


def _build_no_progress_result(
    *,
    start_request: KernelSessionStartRequest,
    session_id: str,
    run_artifact_ref: str | None,
    dashboard: dict[str, object],
    transcript: list[dict[str, object]],
    reason_code: str,
    action_type: str,
    bootstrap_context: dict[str, object],
    iterations: int,
) -> ControllerRunResult:
    from .controller_runtime import ControllerRunResult
    from .controller_proposals import _build_fix_skeleton
    from .controller_transcript import _append_event, _log_controller_event, _persist_controller_transcript

    _append_event(
        transcript,
        event_type="controller_no_progress_stop",
        detail=reason_code,
        payload={
            "reason_code": reason_code,
            "fix": _build_fix_skeleton(
                reason_code=reason_code,
                action_type_raw=action_type,
                bootstrap_context=bootstrap_context,
            ),
            "deed_text_artifact_ref": bootstrap_context.get("deed_text_artifact_ref"),
            "deed_text_excerpt": bootstrap_context.get("deed_text_excerpt"),
        },
    )
    _log_controller_event(
        "controller_no_progress_stop",
        {
            "session_id": session_id,
            "iterations": iterations,
            "reason_code": reason_code,
            "action_type": action_type,
            "deed_text_artifact_ref": bootstrap_context.get("deed_text_artifact_ref"),
        },
    )
    terminal = TerminalOutcome(
        terminal_outcome=TerminalOutcomeKind.FAILED,
        stop_reason=StopReason.NO_PROGRESS,
        success=False,
        reason_code=f"controller_no_progress:{reason_code}",
    )
    transcript_ref = _persist_controller_transcript(
        request_id=start_request.request_id,
        session_id=session_id,
        transcript={"events": transcript},
    )
    return ControllerRunResult(
        terminal=terminal,
        last_dashboard=dashboard,
        transcript_artifact_ref=transcript_ref,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        iterations=iterations,
    )
