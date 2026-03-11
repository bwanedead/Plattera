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
from .controller_guardrails import _encoded_size_bytes, _material_change_fingerprint, _read_str
from .controller_summary import _normalize_iteration_summary_payload, _run_summary_entry_excerpt

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

_TRANSCRIPT_EVENT_HOOK = threading.local()

def set_transcript_event_hook(callback: Callable[[dict[str, object]], None] | None) -> object | None:
    previous = getattr(_TRANSCRIPT_EVENT_HOOK, "callback", None)
    _TRANSCRIPT_EVENT_HOOK.callback = callback
    return previous


def restore_transcript_event_hook(previous: object | None) -> None:
    if previous is None:
        if hasattr(_TRANSCRIPT_EVENT_HOOK, "callback"):
            delattr(_TRANSCRIPT_EVENT_HOOK, "callback")
        return
    _TRANSCRIPT_EVENT_HOOK.callback = previous


def _append_event(
    events: list[dict[str, object]],
    *,
    event_type: str,
    detail: str,
    payload: dict[str, object],
) -> None:
    bounded_detail = _bounded_text(detail, _MAX_EVENT_CHARS)
    payload = _prepare_event_payload_for_transcript(
        event_type=event_type,
        detail=bounded_detail,
        payload=payload,
    )
    event = {
        "event_type": event_type[:64],
        "detail": bounded_detail,
        "payload": _bound_payload(payload),
        "timestamp_epoch_seconds": int(time()),
    }
    events.append(event)
    callback = getattr(_TRANSCRIPT_EVENT_HOOK, "callback", None)
    if callable(callback):
        try:
            callback(dict(event))
        except Exception:
            logger.debug("controller transcript event hook failed", exc_info=True)
    if len(events) > _MAX_EVENTS:
        dropped = len(events) - _MAX_EVENTS
        del events[:dropped]
        events.insert(
            0,
            {
                "event_type": "transcript_truncated",
                "detail": f"dropped_oldest_events_count={dropped}",
                "payload": {},
                "timestamp_epoch_seconds": int(time()),
            },
        )
    while _encoded_size_bytes(events) > _MAX_TOTAL_BYTES and len(events) > 1:
        drop_count = max(1, min(len(events) - 1, len(events) // 8))
        del events[:drop_count]
        marker = {
            "event_type": "transcript_truncated",
            "detail": "dropped_oldest_events_for_size_cap",
            "payload": {},
            "timestamp_epoch_seconds": int(time()),
        }
        if not events or events[0].get("event_type") != "transcript_truncated":
            events.insert(0, marker)


def _prepare_event_payload_for_transcript(
    *,
    event_type: str,
    detail: str,
    payload: dict[str, object],
) -> dict[str, object]:
    out = dict(payload)
    candidate = out.get("display_delta")
    if event_type == "controller_refusal" and candidate is None:
        candidate = _synth_controller_refusal_display_delta(payload=out, detail=detail)
    elif event_type == "kernel_step_result" and candidate is None:
        candidate = _synth_kernel_step_result_display_delta(payload=out, detail=detail)
    display_delta = _sanitize_and_dedupe_display_delta(candidate)
    if display_delta is None:
        out.pop("display_delta", None)
    else:
        out["display_delta"] = display_delta
    return out


def _sanitize_and_dedupe_display_delta(raw_value: object) -> str | None:
    text = _sanitize_display_delta(raw_value)
    if not text:
        return None
    fingerprint = _display_delta_fingerprint(text)
    recent = getattr(_TRANSCRIPT_EVENT_HOOK, "recent_display_delta_fingerprints", None)
    if not isinstance(recent, list):
        recent = []
    for prev in recent:
        if not isinstance(prev, str) or not prev:
            continue
        if fingerprint == prev or fingerprint.startswith(prev) or prev.startswith(fingerprint):
            return None
    recent = [*recent, fingerprint][-8:]
    _TRANSCRIPT_EVENT_HOOK.recent_display_delta_fingerprints = recent
    _TRANSCRIPT_EVENT_HOOK.last_display_delta_fingerprint = fingerprint
    return text


def _sanitize_display_delta(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        text = raw_value
    elif isinstance(raw_value, (dict, list)):
        try:
            text = json.dumps(_bound_payload(raw_value, max_items=8), ensure_ascii=True, separators=(",", ":"))
        except Exception:
            text = repr(raw_value)
    elif isinstance(raw_value, (int, float, bool)):
        text = str(raw_value)
    else:
        text = repr(raw_value)
    text = " ".join(text.replace("\r", "\n").splitlines()[:1]).strip()
    text = " ".join(text.split())
    if not text:
        return None
    sentence_enders = [idx for idx, ch in enumerate(text) if ch in ".!?"]
    if len(sentence_enders) >= 2:
        text = text[: sentence_enders[0] + 1].strip()
    return _bounded_text(text, _MAX_DISPLAY_DELTA_CHARS)


def _display_delta_fingerprint(text: str) -> str:
    normalized = " ".join(text.lower().split())
    normalized = normalized.strip(" \t\r\n.,;:!?-")
    return normalized[:_MAX_DISPLAY_DELTA_CHARS]


def _synth_controller_refusal_display_delta(*, payload: Mapping[str, object], detail: str) -> str | None:
    action_type = _read_str(payload.get("action_type")) or "step"
    refusal = payload.get("refusal")
    reason_code = None
    if isinstance(refusal, dict):
        reason_code = _read_str(refusal.get("reason_code"))
    if reason_code and "repeated_inspection_no_progress" in reason_code:
        return "I stopped repeating the same inspection and need a different next move."
    if reason_code and "repeated_span_open_no_progress" in reason_code:
        return "I stopped reopening the same deed span and need to update the draft or indexing next."
    if reason_code and "semantic_repair_span_loop_no_progress" in reason_code:
        return "I have enough repeated deed excerpts for this repair and need to revise the draft instead of rereading."
    if action_type == ActionType.DRAFT_IR.value:
        return "The draft needs a more complete graph update before it can continue."
    if action_type in {ActionType.COMPILE.value, ActionType.JUDGE.value, ActionType.BUNDLE.value}:
        return "This check could not run yet because a required graph artifact is missing."
    if action_type in {ActionType.GEOREFERENCE.value, ActionType.VALIDATE.value, ActionType.RENDER.value}:
        return "This mapping check needs the prior output artifact before it can continue."
    if "action_not_in_tool_menu" in (reason_code or detail):
        return "I need to choose a step that is currently allowed in this run."
    return "I need to fix the next step details before it can run."


def _synth_kernel_step_result_display_delta(*, payload: Mapping[str, object], detail: str) -> str | None:
    action_type = _read_str(payload.get("action_type")) or "step"
    execution_state = _read_str(payload.get("execution_state")) or detail or "completed"
    refusal = payload.get("refusal")
    if isinstance(refusal, dict) and _read_str(refusal.get("reason_code")):
        return "That step did not complete, so I need to repair the plan and try again."
    if execution_state == StepExecutionState.DEDUPED.value:
        return "That step was already applied, so I am moving on without changing outputs."
    if action_type == ActionType.DRAFT_IR.value:
        return "I updated the deed graph draft so the next checks can measure gaps."
    if action_type in {ActionType.COMPILE.value, ActionType.JUDGE.value}:
        return "I refreshed the current checks so the next move can use the latest gaps."
    if action_type == ActionType.BUNDLE.value:
        return "I packaged the current graph outputs for downstream mapping and review."
    if action_type == ActionType.GEOREFERENCE.value:
        return "I mapped the current parcel output into a georeferenced result."
    if action_type == ActionType.VALIDATE.value:
        return "I ran a validation pass on the mapped output and recorded the result."
    if action_type == ActionType.RENDER.value:
        return "I rendered a map preview artifact for visual review of the mapped output."
    if action_type == ActionType.DECLARE_DONE.value:
        return "I finished the current deed run and recorded the completion decision."
    if action_type in {ActionType.OPEN_TEXT_SPANS.value, ActionType.OPEN_ARTIFACT.value, ActionType.HYDRATE_DEED.value}:
        return "I refreshed the deed source context so the next step can use verified details."
    return "I completed the current step and refreshed the latest run outputs."


def _bounded_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 14]}...[truncated]"


def _bound_payload(value: object, *, max_items: int = 24) -> object:
    if isinstance(value, str):
        return _bounded_text(value, _MAX_EVENT_CHARS)
    if isinstance(value, list):
        trimmed = value[:max_items]
        return [_bound_payload(item, max_items=max_items) for item in trimmed]
    if isinstance(value, dict):
        out: dict[str, object] = {}
        count = 0
        for key, item in value.items():
            if count >= max_items:
                out["__truncated__"] = True
                break
            out[str(key)[:96]] = _bound_payload(item, max_items=max_items)
            count += 1
        return out
    return value


def _proposal_failure_payload(raw: dict[str, object], *, attempt: str, parse_error: str | None) -> dict[str, object]:
    payload = {
        "attempt": attempt,
        "error": _bounded_text(str(raw.get("error", "")), _MAX_ERROR_CHARS),
        "parse_error": _bounded_text(parse_error or "", _MAX_ERROR_CHARS),
    }
    openai_fields = {
        "http_status": raw.get("http_status"),
        "openai_request_id": raw.get("openai_request_id"),
        "error_type": raw.get("error_type"),
        "error_message": raw.get("error_message"),
        "error_param": raw.get("error_param"),
        "error_code": raw.get("error_code"),
        "api_model": raw.get("api_model"),
        "request_flags": raw.get("request_flags"),
    }
    cleaned = {k: v for k, v in openai_fields.items() if v not in (None, "", {}, [])}
    if cleaned:
        payload["openai_error"] = _bound_payload(cleaned)
    structured_data = raw.get("structured_data")
    if isinstance(structured_data, dict):
        payload["structured_data_keys"] = [str(k)[:64] for k in list(structured_data.keys())[:12]]
        try:
            payload["structured_data_excerpt"] = _bounded_text(
                json.dumps(_bound_payload(structured_data), ensure_ascii=True),
                1800,
            )
        except Exception:
            payload["structured_data_excerpt"] = _bounded_text(str(structured_data), 1800)
    text_value = raw.get("text")
    if isinstance(text_value, str) and text_value.strip():
        payload["text_excerpt"] = _bounded_text(text_value, 400)
    tool_calls_seen = raw.get("tool_calls_seen")
    if isinstance(tool_calls_seen, list):
        payload["tool_calls_seen"] = [str(v)[:64] for v in tool_calls_seen[:8]]
    tool_name = raw.get("tool_name")
    if isinstance(tool_name, str) and tool_name:
        payload["tool_name"] = tool_name[:64]
    return payload


def _latest_refs_summary(dashboard: dict[str, object]) -> dict[str, object]:
    latest_refs = dashboard.get("latest_refs")
    if not isinstance(latest_refs, dict):
        return {}
    summary: dict[str, object] = {}
    for key, value in latest_refs.items():
        if isinstance(value, dict):
            artifact_path = value.get("artifact_path")
            if isinstance(artifact_path, str) and artifact_path:
                summary[key] = artifact_path
    return summary


def _log_controller_event(event_type: str, payload: dict[str, object]) -> None:
    try:
        bounded = _bound_payload(payload)
        if not isinstance(bounded, dict):
            bounded = {"payload": bounded}
        logger.info(
            "controller_event %s",
            json.dumps({"event_type": event_type, **bounded}, ensure_ascii=True),
        )
    except Exception:
        logger.info("controller_event %s", event_type)


def _controller_proposal_log_payload(
    *,
    iteration: int,
    action_type: str,
    args: dict[str, object],
    why: str,
    iteration_summary: object | None = None,
    proposal_source: str | None = None,
) -> dict[str, object]:
    normalized_summary = _normalize_iteration_summary_payload(iteration_summary) if iteration_summary is not None else None
    payload = {
        "iteration": iteration,
        "action_type": action_type,
        "arg_keys": sorted(args.keys()),
        "args_material_fingerprint": _material_change_fingerprint(action_type=action_type, args=args),
        "why": _bounded_text(why, 160),
        "iteration_summary_excerpt": _run_summary_entry_excerpt(normalized_summary) if isinstance(normalized_summary, dict) else None,
    }
    if proposal_source:
        payload["proposal_source"] = proposal_source
    return payload


def _controller_refusal_log_payload(
    *,
    iteration: int,
    reason_code: str,
    action_type: str,
    args: dict[str, object],
    missing_inputs: list[str],
    retryable: bool,
    iteration_summary: object | None = None,
) -> dict[str, object]:
    normalized_summary = _normalize_iteration_summary_payload(iteration_summary) if iteration_summary is not None else None
    return {
        "iteration": iteration,
        "reason_code": reason_code,
        "action_type": action_type,
        "arg_keys": sorted(args.keys()),
        "args_material_fingerprint": _material_change_fingerprint(action_type=action_type, args=args),
        "missing_inputs": missing_inputs[:8],
        "retryable": retryable,
        "iteration_summary_excerpt": _run_summary_entry_excerpt(normalized_summary) if isinstance(normalized_summary, dict) else None,
    }


def _persist_controller_transcript(
    *,
    request_id: str,
    session_id: str,
    transcript: dict[str, object],
) -> str:
    root = agent_kernel_artifacts_root() / "controller_transcripts" / request_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{session_id.replace(':', '_')}_{uuid4().hex[:8]}.json"
    fd, tmp_path = tempfile.mkstemp(prefix="controller_transcript_", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            with path.open("w", encoding="utf-8") as f:
                json.dump(transcript, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return str(path)
