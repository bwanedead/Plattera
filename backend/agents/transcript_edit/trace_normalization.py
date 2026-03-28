from __future__ import annotations

from typing import Any

_MAX_EVENT_MESSAGE_CHARS = 220
_MAX_REASON_CHARS = 160


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def as_str(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else None
    return None


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def first_non_empty(*values: Any) -> str | None:
    for value in values:
        parsed = as_str(value)
        if parsed:
            return parsed
    return None


def bounded_text(value: Any, *, max_chars: int) -> str | None:
    parsed = as_str(value)
    if not parsed:
        return None
    if len(parsed) <= max_chars:
        return parsed
    if max_chars <= 16:
        return parsed[:max_chars]
    return f"{parsed[: max_chars - 14]}...[truncated]"


def source_ref(*, primary: str | None, default: str) -> str:
    return first_non_empty(primary, default) or default


def event_kind(*, event: dict[str, Any]) -> str:
    phase = (as_str(event.get("phase")) or "").lower()
    event_type = (as_str(event.get("event_type")) or "").lower()
    if phase in {"starting", "preflight_countdown"}:
        return "request_start"
    if event_type == "blocker_update":
        return "iteration"
    if event_type in {"human_feedback", "human_feedback_needed", "human_resolution_ticket"}:
        return "hitl_escalation"
    if phase in {
        "human_feedback_needed",
        "human_feedback_received",
        "human_feedback_consumed",
        "human_feedback_reused",
        "human_feedback_stale",
        "human_feedback_prompt_superseded",
    }:
        return "hitl_escalation"
    if phase.startswith("ticket_"):
        return "hitl_escalation"
    if phase in {"resolver_attempt", "resolver_outcome", "resolver_move_gate", "resolver_invalid", "plan", "plan_result"}:
        return "model_proposal"
    if phase in {"apply_result", "promote"}:
        return "tool_execution"
    if phase in {"open_spans", "open_spans_result", "investigation_baseline", "investigation_baseline_result"}:
        return "retrieval_evidence"
    if phase in {"audit", "audit_result", "image_verify", "image_verify_result", "final_verify_retry"}:
        return "verification"
    return "iteration"


def event_actor(*, event: dict[str, Any]) -> str:
    event_type = (as_str(event.get("event_type")) or "").lower()
    phase = (as_str(event.get("phase")) or "").lower()
    if event_type in {"human_feedback", "human_resolution_ticket"}:
        return "human"
    if phase == "human_feedback_received":
        return "human"
    if phase in {
        "human_feedback_needed",
        "human_feedback_consumed",
        "human_feedback_reused",
        "human_feedback_stale",
        "human_feedback_prompt_superseded",
    }:
        return "harness"
    if phase.startswith("resolver") or phase.startswith("plan"):
        return "model"
    if phase in {"apply_result", "promote"}:
        return "tool"
    return "harness"


def event_status(*, event: dict[str, Any]) -> str:
    execution_state = (as_str(event.get("execution_state")) or "").lower()
    if execution_state == "waiting":
        return "waiting"
    if execution_state == "failed":
        return "failed"
    if execution_state == "received":
        return "refused" if _is_refusal_event(event) else "completed"
    if execution_state in {"starting", "running", "retrying"}:
        return "running"
    phase = (as_str(event.get("phase")) or "").lower()
    if phase.endswith("_result") or phase in {"resolver_outcome", "resolver_move_gate", "audit_result", "plan_result"}:
        return "completed"
    return "running"


def event_reason_code(*, event: dict[str, Any]) -> str | None:
    detail = as_dict(event.get("detail"))
    return first_non_empty(
        detail.get("reason_code"),
        detail.get("reason"),
        event.get("reason_code"),
        bounded_text(event.get("message"), max_chars=_MAX_REASON_CHARS),
    )


def refs_delta(*, event: dict[str, Any]) -> dict[str, Any]:
    latest_refs = event.get("latest_refs")
    return as_dict(latest_refs) if isinstance(latest_refs, dict) else {}


def source_local_id(*, event: dict[str, Any], fallback: str) -> str:
    return first_non_empty(
        event.get("prompt_id"),
        event.get("ticket_id"),
        event.get("event_type"),
        fallback,
    ) or fallback


def payload_for_stream_event(*, event: dict[str, Any]) -> dict[str, Any]:
    phase = as_str(event.get("phase"))
    event_type_value = as_str(event.get("event_type"))
    payload: dict[str, Any] = {
        "phase": phase,
        "event_type": event_type_value,
        "message_excerpt": bounded_text(event.get("message"), max_chars=_MAX_EVENT_MESSAGE_CHARS),
    }
    for key in ("prompt_id", "replacement_prompt_id", "ticket_id", "decision_key", "lifecycle_state", "blocking"):
        value = event.get(key)
        if value not in (None, "", []):
            payload[key] = value
    detail = as_dict(event.get("detail"))
    if detail:
        evidence_attempts = as_dict(detail.get("evidence_attempts"))
        if evidence_attempts:
            payload["evidence_attempts"] = {
                "open_spans_count": int(evidence_attempts.get("open_spans_count") or 0),
                "image_verify_count": int(evidence_attempts.get("image_verify_count") or 0),
                "retrieval_count": int(evidence_attempts.get("retrieval_count") or 0),
            }
        if "residual_blockers" in detail and isinstance(detail.get("residual_blockers"), list):
            payload["residual_blockers_count"] = len(detail.get("residual_blockers") or [])
        for key in (
            "result_category",
            "move",
            "gate_outcome",
            "gate_reason",
            "plan_reason",
            "op_count",
            "mapping_blocking_count",
            "optional_count",
            "next_recommended_action",
        ):
            value = detail.get(key)
            if value not in (None, "", []):
                payload[key] = value
    return {k: v for k, v in payload.items() if v not in (None, "", {}, [])}


def _is_refusal_event(event: dict[str, Any]) -> bool:
    phase = (as_str(event.get("phase")) or "").lower()
    return phase in {"human_feedback_stale", "resolver_invalid"}
