"""Controller loop for driving the step-driven Agent Kernel."""

from __future__ import annotations

import json
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

from .contracts import NextStepProposal, next_step_json_schema
from .retrieval_intents import classify_retrieval_degradation, map_retrieval_intent_to_inputs

_MAX_CONTROLLER_INPUT_BYTES = 4096
_MAX_EVENTS = 200
_MAX_EVENT_CHARS = 2000
_MAX_TOTAL_BYTES = 262144


class NextStepLLMClient(Protocol):
    """Strict-JSON LLM interface for controller step proposals."""

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

    iterations = 0
    bootstrap_context = _build_bootstrap_context(start_request)
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

        if proposal.action_type.value not in started.tool_menu:
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
                payload={"action_type": proposal.action_type.value},
            )
            continue

        payload_refusal = _validate_controller_inputs(proposal.inputs)
        if payload_refusal is not None:
            last_refusal = payload_refusal
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=payload_refusal.reason_code,
                payload={"refusal": payload_refusal.model_dump(mode="json")},
            )
            continue

        if proposal.action_type == ActionType.DECLARE_DONE and proposal.declare_done is None:
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

        step_inputs = dict(proposal.inputs)
        if proposal.action_type == ActionType.RETRIEVE_EVIDENCE and proposal.retrieval_intent is not None:
            query = str(step_inputs.get("query", "")).strip()
            if query:
                step_inputs = map_retrieval_intent_to_inputs(
                    intent=proposal.retrieval_intent,
                    query=query,
                )
        step_request = KernelStepRequest(
            session_id=session_id,
            idempotency_key=proposal.idempotency_key,
            action_type=proposal.action_type,
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
                "execution_state": step_result.execution_state.value,
                "action_type": proposal.action_type.value,
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
            },
        )

        if proposal.action_type == ActionType.RETRIEVE_EVIDENCE:
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
) -> NextStepProposal | None:
    schema = next_step_json_schema()
    prompt = (
        "Return JSON only. Propose exactly one next kernel step. "
        "Respect tool_menu and refs-not-blobs. "
        f"Observation JSON: {json.dumps(observation, sort_keys=True)}"
    )
    first = llm_client.propose_next_step(model=model, schema=schema, prompt=prompt)
    proposal = _coerce_proposal(first)
    if proposal is not None:
        return proposal
    _append_event(
        transcript,
        event_type="controller_parse_failed",
        detail="first_parse_or_validation_failed",
        payload={"error": str(first.get("error", ""))[:256]},
    )

    repair_prompt = (
        "Your prior output failed schema validation. Return ONLY valid JSON "
        "for NextStepProposal with no markdown."
    )
    second = llm_client.propose_next_step(model=model, schema=schema, prompt=repair_prompt)
    proposal = _coerce_proposal(second)
    if proposal is not None:
        return proposal
    _append_event(
        transcript,
        event_type="controller_parse_failed",
        detail="repair_parse_or_validation_failed",
        payload={"error": str(second.get("error", ""))[:256]},
    )
    return None


def _coerce_proposal(raw: dict[str, object]) -> NextStepProposal | None:
    structured = raw.get("structured_data")
    if isinstance(structured, dict):
        try:
            return NextStepProposal.model_validate(structured)
        except Exception:
            return None
    text = raw.get("text")
    if not isinstance(text, str):
        return None
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return None
        return NextStepProposal.model_validate(parsed)
    except Exception:
        return None


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
    return None


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
        "payload": payload,
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
