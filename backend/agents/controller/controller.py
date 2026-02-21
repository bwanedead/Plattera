"""Controller loop for driving the step-driven Agent Kernel."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any, Protocol
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root

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
    KernelStepProposal,
    coerce_action_type,
    kernel_step_tool_schema,
    validate_action_args,
)
from .retrieval_intents import classify_retrieval_degradation, map_retrieval_intent_to_inputs

_MAX_CONTROLLER_INPUT_BYTES = 4096
_MAX_EVENTS = 200
_MAX_EVENT_CHARS = 2000
_MAX_TOTAL_BYTES = 262144
_MAX_ERROR_CHARS = 1000

logger = logging.getLogger(__name__)


class NextStepLLMClient(Protocol):
    """LLM interface for proposing one controller step."""

    def propose_next_step(
        self,
        *,
        model: str,
        schema: dict[str, object],
        prompt: str,
    ) -> dict[str, object]: ...


class ControllerLoopError(RuntimeError):
    """Raised when controller runtime invariants are violated."""


@dataclass(frozen=True)
class ControllerRunResult:
    terminal: TerminalOutcome
    last_dashboard: dict[str, object]
    transcript_artifact_ref: str
    session_id: str | None
    run_artifact_ref: str | None
    iterations: int


def run_controller_loop(
    *,
    session_manager: KernelSessionManager,
    llm_client: NextStepLLMClient,
    start_request: KernelSessionStartRequest,
    model: str = "gpt-5-mini",
    max_iterations: int = 20,
) -> ControllerRunResult:
    started = session_manager.start_session(start_request)
    transcript: list[dict[str, object]] = []
    last_refusal: KernelRefusal | None = None
    last_result: KernelStepResult | None = None
    session_id = started.session_id
    if started.refusal is not None:
        _append_event(
            transcript,
            event_type="start_refused",
            detail=started.refusal.reason_code,
            payload={"refusal": started.refusal.model_dump(mode="json")},
        )
        terminal = TerminalOutcome(
            terminal_outcome=TerminalOutcomeKind.FAILED,
            stop_reason=started.dashboard.failure_classification.stop_reason
            if started.dashboard is not None
            and started.dashboard.failure_classification.stop_reason is not None
            else StopReason.INTERNAL_ERROR,
            success=False,
            reason_code=started.refusal.reason_code,
        )
        transcript_ref = _persist_controller_transcript(
            request_id=start_request.request_id,
            session_id=session_id or "unknown_session",
            transcript={"events": transcript},
        )
        return ControllerRunResult(
            terminal=terminal,
            last_dashboard=started.dashboard.model_dump(mode="json") if started.dashboard is not None else {},
            transcript_artifact_ref=transcript_ref,
            session_id=session_id,
            run_artifact_ref=started.run_artifact_ref,
            iterations=0,
        )
    if started.dashboard is None or session_id is None:
        raise ControllerLoopError("kernel_start_session_missing_dashboard_or_session")

    bootstrap_context = _build_bootstrap_context(start_request)
    run_header = {
        "request_id": start_request.request_id,
        "session_id": session_id,
        "run_artifact_ref": started.run_artifact_ref,
        "model": model,
        "tool_menu": started.tool_menu,
        "budgets": start_request.budgets.model_dump(mode="json"),
        "dossier_id": start_request.dossier_id,
        "source_entry_ref": start_request.source_entry_ref,
        "bootstrap_context": bootstrap_context,
    }
    _append_event(
        transcript,
        event_type="run_header",
        detail="controller_run_started",
        payload=run_header,
    )
    _log_controller_event(
        "controller_run_started",
        {
            "request_id": start_request.request_id,
            "session_id": session_id,
            "run_artifact_ref": started.run_artifact_ref,
            "model": model,
            "tool_menu": started.tool_menu,
            "budgets": start_request.budgets.model_dump(mode="json"),
            "dossier_id": start_request.dossier_id,
            "source_entry_ref": start_request.source_entry_ref,
            "deed_text_artifact_ref": bootstrap_context.get("deed_text_artifact_ref"),
        },
    )

    iterations = 0
    while iterations < max_iterations:
        iterations += 1
        observation = {
            "session_id": session_id,
            "tool_menu": started.tool_menu,
            "dashboard": started.dashboard.model_dump(mode="json"),
            "bootstrap_context": bootstrap_context,
            "last_refusal": last_refusal.model_dump(mode="json") if last_refusal is not None else None,
            "last_step": last_result.step_record if last_result is not None else None,
        }
        proposal = _propose_next_step(
            llm_client=llm_client,
            model=model,
            observation=observation,
            transcript=transcript,
        )
        if proposal is None:
            break

        action_type = coerce_action_type(proposal.action_type)
        if action_type is None:
            refusal = KernelRefusal(
                reason_code="unknown_action_type",
                missing_inputs=["action_type"],
                retryable=True,
            )
            last_refusal = refusal
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={"action_type": proposal.action_type},
            )
            continue

        if action_type.value not in started.tool_menu:
            refusal = KernelRefusal(
                reason_code="action_not_in_tool_menu",
                missing_inputs=["action_type"],
                retryable=False,
            )
            last_refusal = refusal
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={"action_type": action_type.value},
            )
            continue

        proposal_inputs = dict(proposal.args)
        payload_refusal = _validate_controller_inputs(proposal_inputs)
        if payload_refusal is not None:
            last_refusal = payload_refusal
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=payload_refusal.reason_code,
                payload={"refusal": payload_refusal.model_dump(mode="json")},
            )
            continue

        cleaned_inputs, args_reason, args_missing = validate_action_args(
            action_type=action_type,
            args=proposal_inputs,
        )
        if cleaned_inputs is None:
            refusal = KernelRefusal(
                reason_code=args_reason or f"{action_type.value}_inputs_invalid",
                missing_inputs=args_missing,
                retryable=True,
            )
            last_refusal = refusal
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={"refusal": refusal.model_dump(mode="json")},
            )
            continue

        if action_type == ActionType.DECLARE_DONE and proposal.declare_done is None:
            refusal = KernelRefusal(
                reason_code="declare_done_justification_missing",
                missing_inputs=["declare_done"],
                retryable=True,
            )
            last_refusal = refusal
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={"refusal": refusal.model_dump(mode="json")},
            )
            continue

        step_inputs = cleaned_inputs
        if action_type == ActionType.RETRIEVE_EVIDENCE and proposal.retrieval_intent is not None:
            query = str(step_inputs.get("query", "")).strip()
            if query:
                step_inputs = map_retrieval_intent_to_inputs(
                    intent=proposal.retrieval_intent,
                    query=query,
                )
        step_request = KernelStepRequest(
            session_id=session_id,
            idempotency_key=proposal.idempotency_key,
            action_type=action_type,
            inputs=step_inputs,
            semantic_ready=proposal.semantic_ready,
            notes=proposal.notes,
        )
        step_result = session_manager.step(step_request)
        last_result = step_result
        started.dashboard = step_result.dashboard
        last_refusal = step_result.refusal
        _append_event(
            transcript,
            event_type="kernel_step_result",
            detail=step_result.execution_state.value,
            payload={
                "iteration": iterations,
                "execution_state": step_result.execution_state.value,
                "action_type": action_type.value,
                "idempotency_key": proposal.idempotency_key,
                "refusal": (
                    step_result.refusal.model_dump(mode="json")
                    if step_result.refusal is not None
                    else None
                ),
                "terminal": (
                    step_result.terminal.model_dump(mode="json")
                    if step_result.terminal is not None
                    else None
                ),
                "dashboard_failure_classification": (
                    step_result.dashboard.failure_classification.model_dump(mode="json")
                    if step_result.dashboard is not None
                    else {}
                ),
                "latest_refs": _latest_refs_summary(step_result.dashboard.model_dump(mode="json")),
            },
        )
        _log_controller_event(
            "kernel_step_result",
            {
                "iteration": iterations,
                "session_id": session_id,
                "action_type": action_type.value,
                "idempotency_key": proposal.idempotency_key,
                "execution_state": step_result.execution_state.value,
                "kernel_refusal_reason_code": (
                    step_result.refusal.reason_code if step_result.refusal is not None else None
                ),
                "terminal_stop_reason": (
                    step_result.terminal.stop_reason.value if step_result.terminal is not None else None
                ),
                "dashboard_reason_code": step_result.dashboard.failure_classification.reason_code,
                "latest_refs": _latest_refs_summary(step_result.dashboard.model_dump(mode="json")),
            },
        )

        if action_type == ActionType.RETRIEVE_EVIDENCE:
            reason_code = (
                step_result.dashboard.failure_classification.reason_code
                or (step_result.refusal.reason_code if step_result.refusal is not None else None)
            )
            if reason_code:
                decision = classify_retrieval_degradation(reason_code)
                if decision is not None:
                    _append_event(
                        transcript,
                        event_type="retrieval_degradation",
                        detail=decision.strategy,
                        payload={
                            "reason_code": decision.reason_code,
                            "fallback": decision.fallback,
                        },
                    )

        if step_result.terminal is not None:
            transcript_ref = _persist_controller_transcript(
                request_id=start_request.request_id,
                session_id=session_id,
                transcript={"events": transcript},
            )
            return ControllerRunResult(
                terminal=step_result.terminal,
                last_dashboard=step_result.dashboard.model_dump(mode="json"),
                transcript_artifact_ref=transcript_ref,
                session_id=session_id,
                run_artifact_ref=started.run_artifact_ref,
                iterations=iterations,
            )

        if step_result.execution_state in {StepExecutionState.EXECUTED, StepExecutionState.DEDUPED}:
            continue
        if step_result.execution_state == StepExecutionState.REFUSED:
            continue

    terminal = TerminalOutcome(
        terminal_outcome=TerminalOutcomeKind.FAILED,
        stop_reason=StopReason.INTERNAL_ERROR,
        success=False,
        reason_code="controller_iterations_exhausted_or_parse_failed",
    )
    transcript_ref = _persist_controller_transcript(
        request_id=start_request.request_id,
        session_id=session_id,
        transcript={"events": transcript},
    )
    return ControllerRunResult(
        terminal=terminal,
        last_dashboard=started.dashboard.model_dump(mode="json"),
        transcript_artifact_ref=transcript_ref,
        session_id=session_id,
        run_artifact_ref=started.run_artifact_ref,
        iterations=iterations,
    )


def _propose_next_step(
    *,
    llm_client: NextStepLLMClient,
    model: str,
    observation: dict[str, object],
    transcript: list[dict[str, object]],
) -> KernelStepProposal | None:
    schema = kernel_step_tool_schema()
    prompt = (
        "Propose exactly one next kernel step by calling the `kernel_step` tool. "
        "Respect tool_menu and refs-not-blobs. "
        f"Observation JSON: {json.dumps(observation, sort_keys=True)}"
    )
    first = llm_client.propose_next_step(model=model, schema=schema, prompt=prompt)
    proposal, parse_error = _coerce_proposal(first)
    if proposal is not None:
        return proposal
    first_failure = _proposal_failure_payload(first, attempt="first", parse_error=parse_error)
    _append_event(
        transcript,
        event_type="controller_parse_failed",
        detail="first_parse_or_validation_failed",
        payload=first_failure,
    )
    _log_controller_event("controller_parse_failed", first_failure)

    repair_prompt = (
        "Your prior proposal was invalid. Call `kernel_step` once using this shape: "
        '{"action_type":"...", "args":{}, "idempotency_key":"...", "why":"..."} '
        "Use only actions in tool_menu and include missing required fields. "
        f"Prior parse error: {parse_error or 'unknown'}."
    )
    second = llm_client.propose_next_step(model=model, schema=schema, prompt=repair_prompt)
    proposal, parse_error = _coerce_proposal(second)
    if proposal is not None:
        return proposal
    second_failure = _proposal_failure_payload(second, attempt="repair", parse_error=parse_error)
    _append_event(
        transcript,
        event_type="controller_parse_failed",
        detail="repair_parse_or_validation_failed",
        payload=second_failure,
    )
    _log_controller_event("controller_parse_failed", second_failure)
    return None


def _coerce_proposal(raw: dict[str, object]) -> tuple[KernelStepProposal | None, str | None]:
    structured = raw.get("structured_data")
    if isinstance(structured, dict):
        try:
            validated = KernelStepProposal.model_validate(structured)
            return validated, None
        except Exception as exc:
            try:
                legacy = structured.get("proposal")
                if isinstance(legacy, dict):
                    validated = KernelStepProposal.model_validate(legacy)
                    return validated, None
                return None, f"schema_validation_failed:{type(exc).__name__}"
            except Exception:
                return None, f"schema_validation_failed:{type(exc).__name__}"
    text = raw.get("text")
    if not isinstance(text, str):
        return None, "response_missing_text"
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return None, "json_not_object"
        try:
            validated = KernelStepProposal.model_validate(parsed)
            return validated, None
        except Exception:
            legacy = parsed.get("proposal")
            if isinstance(legacy, dict):
                validated = KernelStepProposal.model_validate(legacy)
                return validated, None
            return None, "schema_validation_failed:ValidationError"
    except json.JSONDecodeError as exc:
        return None, f"json_parse_failed:{exc.msg}"
    except Exception as exc:
        return None, f"schema_validation_failed:{type(exc).__name__}"


def _validate_controller_inputs(inputs: dict[str, object]) -> KernelRefusal | None:
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) > _MAX_CONTROLLER_INPUT_BYTES:
        return KernelRefusal(
            reason_code="controller_inputs_payload_too_large",
            retryable=False,
            blocked_by_invariant=True,
        )
    if _contains_large_geometry(inputs):
        return KernelRefusal(
            reason_code="controller_inputs_include_large_geometry_blob",
            retryable=False,
            blocked_by_invariant=True,
        )
    if _contains_excessive_depth(inputs):
        return KernelRefusal(
            reason_code="controller_inputs_depth_exceeded",
            retryable=False,
            blocked_by_invariant=True,
        )
    return None


def _contains_excessive_depth(value: object, *, depth: int = 0, max_depth: int = 8) -> bool:
    if depth > max_depth:
        return True
    if isinstance(value, dict):
        return any(_contains_excessive_depth(v, depth=depth + 1, max_depth=max_depth) for v in value.values())
    if isinstance(value, list):
        return any(_contains_excessive_depth(v, depth=depth + 1, max_depth=max_depth) for v in value)
    return False


def _build_bootstrap_context(start_request: KernelSessionStartRequest) -> dict[str, object]:
    context: dict[str, object] = {
        "dossier_id": start_request.dossier_id,
        "source_entry_ref": start_request.source_entry_ref,
        "initial_ir_ref": start_request.initial_ir_ref,
    }
    graph = start_request.initial_graph_json if isinstance(start_request.initial_graph_json, dict) else None
    if graph is not None:
        metadata = graph.get("metadata")
        if isinstance(metadata, dict):
            deed_ref = metadata.get("deed_text_artifact_ref")
            excerpt = metadata.get("deed_text_excerpt")
            if isinstance(deed_ref, str) and deed_ref:
                context["deed_text_artifact_ref"] = deed_ref
            if isinstance(excerpt, str) and excerpt:
                context["deed_text_excerpt"] = excerpt[:512]
    return context


def _contains_large_geometry(value: object, parent_key: str = "") -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            if key_lower in {"geometry", "coordinates", "rings", "vertices", "polygon"}:
                if isinstance(nested, list) and len(nested) > 64:
                    return True
            if _contains_large_geometry(nested, key_lower):
                return True
        return False
    if isinstance(value, list):
        if parent_key in {"geometry", "coordinates", "rings", "vertices", "polygon"} and len(value) > 64:
            return True
        for nested in value:
            if _contains_large_geometry(nested, parent_key):
                return True
    return False


def _append_event(
    events: list[dict[str, object]],
    *,
    event_type: str,
    detail: str,
    payload: dict[str, object],
) -> None:
    bounded_detail = _bounded_text(detail, _MAX_EVENT_CHARS)
    event = {
        "event_type": event_type[:64],
        "detail": bounded_detail,
        "payload": _bound_payload(payload),
        "timestamp_epoch_seconds": int(time()),
    }
    events.append(event)
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


def _encoded_size_bytes(events: list[dict[str, object]]) -> int:
    return len(json.dumps({"events": events}, ensure_ascii=True).encode("utf-8"))


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
