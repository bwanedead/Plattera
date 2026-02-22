"""Controller loop for driving the step-driven Agent Kernel."""

from __future__ import annotations

import json
import hashlib
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
    action_how_to_guide,
    coerce_action_type,
    kernel_step_tool_schema,
    tool_cheatsheet_entries,
    validate_action_args,
)
from .digests import build_fallback_iteration_digest, persist_iteration_digest
from .retrieval_intents import classify_retrieval_degradation, map_retrieval_intent_to_inputs

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


class IterationDigestClient(Protocol):
    """Cheap summarizer interface for compact per-iteration digest memory."""

    def summarize_iteration_digest(
        self,
        *,
        payload: dict[str, object],
        model: str = "gpt-5-mini",
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
    digest_client: IterationDigestClient | None = None,
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
    run_summary_ref: str | None = None
    run_summary_excerpt: str | None = None
    refusal_streak = 0
    previous_refusal_signature: str | None = None
    executed_steps = 0
    phase_hint = "bootstrap"
    last_summary_phase = phase_hint
    recent_digest_memory: list[dict[str, object]] = []
    last_refusal_action_type_raw: str | None = None
    while iterations < max_iterations:
        iterations += 1
        context_packet = _build_context_packet(
            session_id=session_id,
            tool_menu=started.tool_menu,
            bootstrap_context=bootstrap_context,
            dashboard=started.dashboard.model_dump(mode="json"),
            transcript=transcript,
            last_refusal=last_refusal,
            last_refusal_action_type_raw=last_refusal_action_type_raw,
            last_step_result=last_result,
            run_summary_ref=run_summary_ref,
            run_summary_excerpt=run_summary_excerpt,
            phase_hint=phase_hint,
            recent_digest_memory=recent_digest_memory,
        )
        proposal = _propose_next_step(
            llm_client=llm_client,
            model=model,
            observation=context_packet,
            transcript=transcript,
        )
        if proposal is None:
            break
        _append_event(
            transcript,
            event_type="agent_proposed_step",
            detail=proposal.action_type,
            payload={
                "action_type": proposal.action_type,
                "args": proposal.args,
                "why": proposal.why,
            },
        )
        _log_controller_event(
            "agent_proposed_step",
            _controller_proposal_log_payload(
                iteration=iterations,
                action_type=proposal.action_type,
                args=proposal.args,
                why=proposal.why,
            ),
        )

        action_type = coerce_action_type(proposal.action_type)
        if action_type is None:
            refusal = KernelRefusal(
                reason_code="unknown_action_type",
                missing_inputs=["action_type"],
                retryable=True,
            )
            last_refusal = refusal
            last_refusal_action_type_raw = proposal.action_type
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={
                    "action_type": proposal.action_type,
                    "fix": _build_fix_skeleton(
                        reason_code=refusal.reason_code,
                        action_type_raw=proposal.action_type,
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=proposal.action_type,
                        reason_code=refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=refusal.reason_code,
                    action_type=proposal.action_type,
                    args=proposal.args,
                    missing_inputs=refusal.missing_inputs,
                    retryable=refusal.retryable,
                ),
            )
            refusal_streak, previous_refusal_signature = _update_refusal_streak(
                refusal_streak=refusal_streak,
                previous_signature=previous_refusal_signature,
                reason_code=refusal.reason_code,
                action_type=proposal.action_type,
                args=proposal.args,
            )
            if refusal_streak >= 2:
                run_summary_ref, run_summary_excerpt = _persist_run_summary(
                    request_id=start_request.request_id,
                    session_id=session_id,
                    phase_hint=phase_hint,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    last_refusal=refusal.model_dump(mode="json"),
                    transcript=transcript,
                )
            if refusal_streak >= _MAX_REFUSAL_STREAK:
                return _build_no_progress_result(
                    start_request=start_request,
                    session_id=session_id,
                    run_artifact_ref=started.run_artifact_ref,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    transcript=transcript,
                    reason_code=refusal.reason_code,
                    action_type=proposal.action_type,
                    bootstrap_context=bootstrap_context,
                    iterations=iterations,
                )
            recent_digest_memory = _maybe_create_iteration_digest(
                digest_client=digest_client,
                request_id=start_request.request_id,
                session_id=session_id,
                iteration=iterations,
                context_packet=context_packet,
                phase_hint=phase_hint,
                proposal=proposal,
                outcome_kind="controller_refusal",
                outcome_payload={"reason_code": refusal.reason_code, "missing_inputs": refusal.missing_inputs},
                recent_digest_memory=recent_digest_memory,
            )
            continue

        if action_type.value not in started.tool_menu:
            refusal = KernelRefusal(
                reason_code="action_not_in_tool_menu",
                missing_inputs=["action_type"],
                retryable=False,
            )
            last_refusal = refusal
            last_refusal_action_type_raw = action_type.value
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={
                    "action_type": action_type.value,
                    "fix": _build_fix_skeleton(
                        reason_code=refusal.reason_code,
                        action_type_raw=action_type.value,
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=action_type,
                        reason_code=refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    args=proposal.args,
                    missing_inputs=refusal.missing_inputs,
                    retryable=refusal.retryable,
                ),
            )
            refusal_streak, previous_refusal_signature = _update_refusal_streak(
                refusal_streak=refusal_streak,
                previous_signature=previous_refusal_signature,
                reason_code=refusal.reason_code,
                action_type=action_type.value,
                args=proposal.args,
            )
            if refusal_streak >= 2:
                run_summary_ref, run_summary_excerpt = _persist_run_summary(
                    request_id=start_request.request_id,
                    session_id=session_id,
                    phase_hint=phase_hint,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    last_refusal=refusal.model_dump(mode="json"),
                    transcript=transcript,
                )
            if refusal_streak >= _MAX_REFUSAL_STREAK:
                return _build_no_progress_result(
                    start_request=start_request,
                    session_id=session_id,
                    run_artifact_ref=started.run_artifact_ref,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    transcript=transcript,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    bootstrap_context=bootstrap_context,
                    iterations=iterations,
                )
            recent_digest_memory = _maybe_create_iteration_digest(
                digest_client=digest_client,
                request_id=start_request.request_id,
                session_id=session_id,
                iteration=iterations,
                context_packet=context_packet,
                phase_hint=phase_hint,
                proposal=proposal,
                outcome_kind="controller_refusal",
                outcome_payload={"reason_code": refusal.reason_code, "missing_inputs": refusal.missing_inputs},
                recent_digest_memory=recent_digest_memory,
            )
            continue

        proposal_inputs = dict(proposal.args)
        proposal_inputs, autofill_applied = _autofill_known_args(
            action_type=action_type,
            args=proposal_inputs,
            bootstrap_context=bootstrap_context,
            dashboard=started.dashboard.model_dump(mode="json"),
        )
        if autofill_applied:
            _append_event(
                transcript,
                event_type="controller_autofill",
                detail=action_type.value,
                payload={"action_type": action_type.value, "filled": sorted(autofill_applied), "args": proposal_inputs},
            )
            _log_controller_event(
                "controller_autofill",
                {
                    "iteration": iterations,
                    "action_type": action_type.value,
                    "filled": sorted(autofill_applied),
                    "arg_keys": sorted(proposal_inputs.keys()),
                },
            )
        payload_refusal = _validate_controller_inputs(proposal_inputs)
        if payload_refusal is not None:
            last_refusal = payload_refusal
            last_refusal_action_type_raw = action_type.value
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=payload_refusal.reason_code,
                payload={
                    "refusal": payload_refusal.model_dump(mode="json"),
                    "fix": _build_fix_skeleton(
                        reason_code=payload_refusal.reason_code,
                        action_type_raw=action_type.value,
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=action_type,
                        reason_code=payload_refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=payload_refusal.reason_code,
                    action_type=action_type.value,
                    args=proposal_inputs,
                    missing_inputs=payload_refusal.missing_inputs,
                    retryable=payload_refusal.retryable,
                ),
            )
            refusal_streak, previous_refusal_signature = _update_refusal_streak(
                refusal_streak=refusal_streak,
                previous_signature=previous_refusal_signature,
                reason_code=payload_refusal.reason_code,
                action_type=action_type.value,
                args=proposal_inputs,
            )
            if refusal_streak >= 2:
                run_summary_ref, run_summary_excerpt = _persist_run_summary(
                    request_id=start_request.request_id,
                    session_id=session_id,
                    phase_hint=phase_hint,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    last_refusal=payload_refusal.model_dump(mode="json"),
                    transcript=transcript,
                )
            if refusal_streak >= _MAX_REFUSAL_STREAK:
                return _build_no_progress_result(
                    start_request=start_request,
                    session_id=session_id,
                    run_artifact_ref=started.run_artifact_ref,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    transcript=transcript,
                    reason_code=payload_refusal.reason_code,
                    action_type=action_type.value,
                    bootstrap_context=bootstrap_context,
                    iterations=iterations,
                )
            recent_digest_memory = _maybe_create_iteration_digest(
                digest_client=digest_client,
                request_id=start_request.request_id,
                session_id=session_id,
                iteration=iterations,
                context_packet=context_packet,
                phase_hint=phase_hint,
                proposal=proposal,
                outcome_kind="controller_refusal",
                outcome_payload={"reason_code": payload_refusal.reason_code, "missing_inputs": payload_refusal.missing_inputs},
                recent_digest_memory=recent_digest_memory,
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
            last_refusal_action_type_raw = action_type.value
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={
                    "refusal": refusal.model_dump(mode="json"),
                    "fix": _build_fix_skeleton(
                        reason_code=refusal.reason_code,
                        action_type_raw=action_type.value,
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=action_type,
                        reason_code=refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    args=proposal_inputs,
                    missing_inputs=refusal.missing_inputs,
                    retryable=refusal.retryable,
                ),
            )
            refusal_streak, previous_refusal_signature = _update_refusal_streak(
                refusal_streak=refusal_streak,
                previous_signature=previous_refusal_signature,
                reason_code=refusal.reason_code,
                action_type=action_type.value,
                args=proposal_inputs,
            )
            if refusal_streak >= 2:
                run_summary_ref, run_summary_excerpt = _persist_run_summary(
                    request_id=start_request.request_id,
                    session_id=session_id,
                    phase_hint=phase_hint,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    last_refusal=refusal.model_dump(mode="json"),
                    transcript=transcript,
                )
            if refusal_streak >= _MAX_REFUSAL_STREAK:
                return _build_no_progress_result(
                    start_request=start_request,
                    session_id=session_id,
                    run_artifact_ref=started.run_artifact_ref,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    transcript=transcript,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    bootstrap_context=bootstrap_context,
                    iterations=iterations,
                )
            recent_digest_memory = _maybe_create_iteration_digest(
                digest_client=digest_client,
                request_id=start_request.request_id,
                session_id=session_id,
                iteration=iterations,
                context_packet=context_packet,
                phase_hint=phase_hint,
                proposal=proposal,
                outcome_kind="controller_refusal",
                outcome_payload={"reason_code": refusal.reason_code, "missing_inputs": refusal.missing_inputs},
                recent_digest_memory=recent_digest_memory,
            )
            continue

        if action_type == ActionType.DECLARE_DONE and proposal.declare_done is None:
            refusal = KernelRefusal(
                reason_code="declare_done_justification_missing",
                missing_inputs=["declare_done"],
                retryable=True,
            )
            last_refusal = refusal
            last_refusal_action_type_raw = action_type.value
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={
                    "refusal": refusal.model_dump(mode="json"),
                    "fix": _build_fix_skeleton(
                        reason_code=refusal.reason_code,
                        action_type_raw=action_type.value,
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=action_type,
                        reason_code=refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    args=cleaned_inputs,
                    missing_inputs=refusal.missing_inputs,
                    retryable=refusal.retryable,
                ),
            )
            refusal_streak, previous_refusal_signature = _update_refusal_streak(
                refusal_streak=refusal_streak,
                previous_signature=previous_refusal_signature,
                reason_code=refusal.reason_code,
                action_type=action_type.value,
                args=cleaned_inputs,
            )
            if refusal_streak >= 2:
                run_summary_ref, run_summary_excerpt = _persist_run_summary(
                    request_id=start_request.request_id,
                    session_id=session_id,
                    phase_hint=phase_hint,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    last_refusal=refusal.model_dump(mode="json"),
                    transcript=transcript,
                )
            if refusal_streak >= _MAX_REFUSAL_STREAK:
                return _build_no_progress_result(
                    start_request=start_request,
                    session_id=session_id,
                    run_artifact_ref=started.run_artifact_ref,
                    dashboard=started.dashboard.model_dump(mode="json"),
                    transcript=transcript,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    bootstrap_context=bootstrap_context,
                    iterations=iterations,
                )
            recent_digest_memory = _maybe_create_iteration_digest(
                digest_client=digest_client,
                request_id=start_request.request_id,
                session_id=session_id,
                iteration=iterations,
                context_packet=context_packet,
                phase_hint=phase_hint,
                proposal=proposal,
                outcome_kind="controller_refusal",
                outcome_payload={"reason_code": refusal.reason_code, "missing_inputs": refusal.missing_inputs},
                recent_digest_memory=recent_digest_memory,
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
        computed_idempotency_key = _compute_controller_idempotency_key(
            session_id=session_id,
            iteration=iterations,
            action_type=action_type.value,
            inputs=step_inputs,
        )
        step_request = KernelStepRequest(
            session_id=session_id,
            idempotency_key=computed_idempotency_key,
            action_type=action_type,
            inputs=step_inputs,
            semantic_ready=proposal.semantic_ready,
            notes=proposal.notes,
        )
        step_result = session_manager.step(step_request)
        last_result = step_result
        started.dashboard = step_result.dashboard
        last_refusal = step_result.refusal
        last_refusal_action_type_raw = action_type.value if step_result.refusal is not None else None
        _append_event(
            transcript,
            event_type="kernel_step_result",
            detail=step_result.execution_state.value,
            payload={
                "iteration": iterations,
                "execution_state": step_result.execution_state.value,
                "action_type": action_type.value,
                "idempotency_key": computed_idempotency_key,
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
                "idempotency_key": computed_idempotency_key,
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
        phase_hint = _infer_phase_hint(step_result.dashboard.model_dump(mode="json"))
        if phase_hint != last_summary_phase:
            run_summary_ref, run_summary_excerpt = _persist_run_summary(
                request_id=start_request.request_id,
                session_id=session_id,
                phase_hint=phase_hint,
                dashboard=step_result.dashboard.model_dump(mode="json"),
                last_refusal=last_refusal.model_dump(mode="json") if last_refusal is not None else None,
                transcript=transcript,
            )
            last_summary_phase = phase_hint
        if step_result.execution_state == StepExecutionState.EXECUTED:
            refusal_streak = 0
            previous_refusal_signature = None
            executed_steps += 1
        elif step_result.refusal is not None:
            refusal_streak, previous_refusal_signature = _update_refusal_streak(
                refusal_streak=refusal_streak,
                previous_signature=previous_refusal_signature,
                reason_code=step_result.refusal.reason_code,
                action_type=action_type.value,
                args=step_inputs,
            )
            if refusal_streak >= 2:
                run_summary_ref, run_summary_excerpt = _persist_run_summary(
                    request_id=start_request.request_id,
                    session_id=session_id,
                    phase_hint=phase_hint,
                    dashboard=step_result.dashboard.model_dump(mode="json"),
                    last_refusal=step_result.refusal.model_dump(mode="json"),
                    transcript=transcript,
                )
            if refusal_streak >= _MAX_REFUSAL_STREAK:
                return _build_no_progress_result(
                    start_request=start_request,
                    session_id=session_id,
                    run_artifact_ref=started.run_artifact_ref,
                    dashboard=step_result.dashboard.model_dump(mode="json"),
                    transcript=transcript,
                    reason_code=step_result.refusal.reason_code,
                    action_type=action_type.value,
                    bootstrap_context=bootstrap_context,
                    iterations=iterations,
                )
        recent_digest_memory = _maybe_create_iteration_digest(
            digest_client=digest_client,
            request_id=start_request.request_id,
            session_id=session_id,
            iteration=iterations,
            context_packet=context_packet,
            phase_hint=phase_hint,
            proposal=proposal,
            outcome_kind=(
                "kernel_refusal" if step_result.refusal is not None else "executed"
                if step_result.execution_state == StepExecutionState.EXECUTED
                else "deduped"
            ),
            outcome_payload={
                "execution_state": step_result.execution_state.value,
                "reason_code": (
                    step_result.refusal.reason_code
                    if step_result.refusal is not None
                    else (step_result.terminal.reason_code if step_result.terminal is not None else None)
                ),
                "missing_inputs": step_result.refusal.missing_inputs if step_result.refusal is not None else [],
                "latest_refs": _latest_refs_summary(step_result.dashboard.model_dump(mode="json")),
            },
            recent_digest_memory=recent_digest_memory,
            executed_steps=executed_steps,
        )

        if executed_steps > 0 and executed_steps % _RUN_SUMMARY_EVERY_EXECUTED_STEPS == 0:
            run_summary_ref, run_summary_excerpt = _persist_run_summary(
                request_id=start_request.request_id,
                session_id=session_id,
                phase_hint=phase_hint,
                dashboard=step_result.dashboard.model_dump(mode="json"),
                last_refusal=last_refusal.model_dump(mode="json") if last_refusal is not None else None,
                transcript=transcript,
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
        "Respect tool_menu and refs-not-blobs. Use the Context Packet below. "
        f"ContextPacket JSON: {json.dumps(observation, sort_keys=True)}"
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
        "Use only actions in tool_menu and include missing required fields from last_refusal.fix.required_fields. "
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
    deed_text_full = _read_deed_text_from_artifact_ref(context.get("deed_text_artifact_ref"))
    if deed_text_full is not None:
        context["deed_text_full"] = deed_text_full
    return context


def _read_deed_text_from_artifact_ref(raw_ref: object) -> str | None:
    if not isinstance(raw_ref, str) or not raw_ref.strip():
        return None
    try:
        path = Path(raw_ref).resolve()
        root = agent_kernel_artifacts_root().resolve()
        if path != root and root not in path.parents:
            return None
        if not path.exists() or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        text = payload.get("text")
        if isinstance(text, str) and text:
            return text
    except Exception:
        return None
    return None


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


def _build_context_packet(
    *,
    session_id: str,
    tool_menu: list[str],
    bootstrap_context: dict[str, object],
    dashboard: dict[str, object],
    transcript: list[dict[str, object]],
    last_refusal: KernelRefusal | None,
    last_refusal_action_type_raw: str | None,
    last_step_result: KernelStepResult | None,
    run_summary_ref: str | None,
    run_summary_excerpt: str | None,
    phase_hint: str,
    recent_digest_memory: list[dict[str, object]],
) -> dict[str, object]:
    latest_refs = _latest_refs_summary(dashboard)
    recent_trace = _extract_recent_trace(transcript)
    progress = {
        "latest_refs": latest_refs,
        "budgets_remaining": dashboard.get("budgets_remaining", {}),
        "gap_summary": _compact_gap_summary(dashboard.get("gap_summary")),
        "claimability": dashboard.get("claimability", {}),
    }
    packet_inputs = {
        "dossier_id": bootstrap_context.get("dossier_id"),
        "source_entry_ref": bootstrap_context.get("source_entry_ref"),
        "deed_text_excerpt": bootstrap_context.get("deed_text_excerpt"),
        "deed_text_artifact_ref": bootstrap_context.get("deed_text_artifact_ref"),
        "deed_text_full": bootstrap_context.get("deed_text_full"),
        "initial_ir_ref": bootstrap_context.get("initial_ir_ref"),
        "latest_ir_ref": latest_refs.get("ir_ref"),
    }
    packet = {
        "session_id": session_id,
        "tool_menu": tool_menu,
        "inputs": packet_inputs,
        "progress": progress,
        "working_memory": {
            "phase_hint": phase_hint,
            "plan_bullets": _phase_plan_bullets(phase_hint),
        },
        "memory": _digest_memory_payload(recent_digest_memory),
        "tool_cheatsheet": tool_cheatsheet_entries(tool_menu=tool_menu, context_inputs=packet_inputs),
        "recent_trace": recent_trace,
        "last_refusal": _last_refusal_payload(
            last_refusal,
            last_refusal_action_type_raw=last_refusal_action_type_raw,
            last_step_result=last_step_result,
            bootstrap_context=bootstrap_context,
            context_inputs=packet_inputs,
        ),
        "artifacts_inline": _inline_artifact_hints(latest_refs, bootstrap_context=bootstrap_context),
        "run_summary": {
            "run_summary_ref": run_summary_ref,
            "excerpt": run_summary_excerpt,
        },
    }
    if not isinstance(packet, dict):
        return packet
    bounded = _bound_payload(packet, max_items=24)
    if isinstance(bounded, dict):
        deed_text_full = bootstrap_context.get("deed_text_full")
        inputs = bounded.get("inputs")
        if isinstance(inputs, dict) and isinstance(deed_text_full, str):
            inputs["deed_text_full"] = deed_text_full
    return bounded


def _compact_gap_summary(gap_summary: object) -> dict[str, object]:
    if not isinstance(gap_summary, dict):
        return {}
    top_gap_kinds = gap_summary.get("top_gap_kinds")
    top_reason_codes = gap_summary.get("top_reason_codes")
    counts = gap_summary.get("gap_counts_by_kind")
    return {
        "top_gap_kinds": top_gap_kinds[:_MAX_GAP_KINDS] if isinstance(top_gap_kinds, list) else [],
        "top_reason_codes": top_reason_codes[:_MAX_REASON_CODES] if isinstance(top_reason_codes, list) else [],
        "gap_counts_by_kind": counts if isinstance(counts, dict) else {},
    }


def _extract_recent_trace(transcript: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for event in reversed(transcript):
        et = str(event.get("event_type", ""))
        if et not in {"kernel_step_result", "controller_refusal", "controller_parse_failed"}:
            continue
        payload = event.get("payload")
        out.append(
            {
                "event_type": et,
                "detail": str(event.get("detail", ""))[:120],
                "action_type": payload.get("action_type") if isinstance(payload, dict) else None,
                "reason_code": _extract_reason_code_from_payload(payload),
            }
        )
        if len(out) >= _MAX_TRACE_ITEMS:
            break
    out.reverse()
    return out


def _extract_reason_code_from_payload(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    refusal = payload.get("refusal")
    if isinstance(refusal, dict):
        reason = refusal.get("reason_code")
        if isinstance(reason, str):
            return reason
    reason = payload.get("reason_code")
    if isinstance(reason, str):
        return reason
    return None


def _phase_plan_bullets(phase_hint: str) -> list[str]:
    plans: dict[str, list[str]] = {
        "bootstrap": [
            "If deed text ref is missing, hydrate deed first.",
            "Draft minimal FeatureGraph IR from deed.",
            "Compile, then judge for gap diagnosis.",
            "Bundle after IR stabilizes.",
        ],
        "author_ir": [
            "Produce or update IR with minimal valid graph structure.",
            "Prefer refs to prior artifacts, avoid blob payloads.",
            "Compile after each meaningful IR change.",
        ],
        "verify": [
            "Judge latest IR for gaps.",
            "Patch or re-draft only to address explicit gaps.",
            "Bundle once compile/judge are present.",
        ],
        "declare_candidate": [
            "Ensure compile/judge/bundle refs are available.",
            "Provide semantic justification with evidence links and assumptions.",
            "Attempt DECLARE_DONE when claimability is ready.",
        ],
    }
    selected = plans.get(phase_hint, plans["bootstrap"])
    return selected[:_MAX_PLAN_BULLETS]


def _last_refusal_payload(
    last_refusal: KernelRefusal | None,
    *,
    last_refusal_action_type_raw: str | None,
    last_step_result: KernelStepResult | None,
    bootstrap_context: dict[str, object] | None,
    context_inputs: dict[str, object],
) -> dict[str, object] | None:
    if last_refusal is None:
        return None
    action_type_raw = (
        last_refusal_action_type_raw
        or ("hydrate_deed" if "deed" in ",".join(last_refusal.missing_inputs).lower() else "open_artifact")
    )
    payload = last_refusal.model_dump(mode="json")
    rejected_meta = _extract_rejected_graph_refusal_meta(last_step_result)
    if rejected_meta:
        payload.update(rejected_meta)
    payload["how_to"] = action_how_to_guide(
        action_type=action_type_raw,
        reason_code=last_refusal.reason_code,
        context_inputs=context_inputs,
    )
    payload["fix"] = _build_fix_skeleton(
        reason_code=last_refusal.reason_code,
        action_type_raw=action_type_raw,
        bootstrap_context=bootstrap_context,
    )
    return payload


def _extract_rejected_graph_refusal_meta(
    last_step_result: KernelStepResult | None,
) -> dict[str, object] | None:
    if last_step_result is None or last_step_result.execution_state != StepExecutionState.REFUSED:
        return None
    step_record = last_step_result.step_record
    if not isinstance(step_record, dict):
        return None
    outputs_inline = step_record.get("outputs_inline")
    if not isinstance(outputs_inline, dict):
        return None
    out: dict[str, object] = {}
    rejected_ref = outputs_inline.get("rejected_graph_artifact_ref")
    if isinstance(rejected_ref, dict):
        artifact_path = rejected_ref.get("artifact_path")
        if isinstance(artifact_path, str):
            out["rejected_graph_artifact_ref"] = {"artifact_path": artifact_path}
    elif isinstance(rejected_ref, str):
        out["rejected_graph_artifact_ref"] = {"artifact_path": rejected_ref}
    rejected_summary = outputs_inline.get("rejected_graph_summary")
    if isinstance(rejected_summary, dict):
        out["rejected_graph_summary"] = _bound_payload(rejected_summary, max_items=12)
    elif isinstance(rejected_summary, str):
        out["rejected_graph_summary"] = {"summary": _bounded_text(rejected_summary, 400)}
    if out:
        return out
    return None


def _digest_memory_payload(recent_digest_memory: list[dict[str, object]]) -> dict[str, object]:
    if not recent_digest_memory:
        return {
            "last_digest_ref": None,
            "last_digest_excerpt": None,
            "recent_digests_excerpts": [],
        }
    last = recent_digest_memory[-1]
    return {
        "last_digest_ref": last.get("digest_ref"),
        "last_digest_excerpt": last.get("digest_excerpt"),
        "recent_digests_excerpts": [d.get("digest_excerpt") for d in recent_digest_memory[-5:] if d.get("digest_excerpt")],
    }


def _inline_artifact_hints(
    latest_refs: dict[str, object],
    *,
    bootstrap_context: dict[str, object],
) -> dict[str, object]:
    hints: dict[str, object] = {}
    ir_ref = latest_refs.get("ir_ref")
    if isinstance(ir_ref, str):
        hints["ir_hint"] = _safe_artifact_hint(ir_ref, kind="ir")
    judge_ref = latest_refs.get("judge_ref")
    if isinstance(judge_ref, str):
        hints["judge_hint"] = _safe_artifact_hint(judge_ref, kind="judge")
    deed_ref = latest_refs.get("deed_text_artifact_ref")
    if not isinstance(deed_ref, str):
        deed_ref = bootstrap_context.get("deed_text_artifact_ref")
    if isinstance(deed_ref, str):
        hints["deed_hint"] = _safe_artifact_hint(deed_ref, kind="deed")
    return hints


def _safe_artifact_hint(path_value: str, *, kind: str) -> dict[str, object]:
    try:
        path = Path(path_value).resolve()
        root = agent_kernel_artifacts_root().resolve()
        if path != root and root not in path.parents:
            return {"kind": kind, "status": "blocked_path"}
    except Exception:
        return {"kind": kind, "status": "blocked_path"}
    if not path.exists():
        return {"kind": kind, "status": "missing"}
    try:
        size = path.stat().st_size
    except Exception:
        return {"kind": kind, "status": "unreadable"}
    if size > _MAX_HINT_FILE_BYTES:
        return {"kind": kind, "status": "too_large"}
    try:
        with path.open("rb") as f:
            raw_bytes = f.read(_MAX_HINT_READ_BYTES + 1)
    except Exception:
        return {"kind": kind, "status": "unreadable"}
    if len(raw_bytes) > _MAX_HINT_READ_BYTES:
        return {"kind": kind, "status": "too_large"}
    try:
        raw = raw_bytes.decode("utf-8")
    except Exception:
        return {"kind": kind, "status": "unreadable"}
    try:
        payload = json.loads(raw)
    except Exception:
        return {"kind": kind, "status": "text", "excerpt": _bounded_text(raw, 256)}
    if kind == "judge" and isinstance(payload, dict):
        report = payload.get("report")
        if isinstance(report, dict):
            gaps = report.get("gaps")
            if isinstance(gaps, list):
                top = []
                for gap in gaps[:3]:
                    if isinstance(gap, dict):
                        top.append(
                            {
                                "kind": gap.get("kind"),
                                "reason_code": gap.get("reason_code"),
                                "node_id": gap.get("node_id"),
                            }
                        )
                return {"kind": kind, "status": "ok", "top_gaps": top}
    if kind == "ir" and isinstance(payload, dict):
        graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
        if isinstance(graph, dict):
            nodes = graph.get("nodes")
            node_preview = []
            if isinstance(nodes, list):
                for node in nodes[:3]:
                    if isinstance(node, dict):
                        node_preview.append(
                            {
                                "id": node.get("id"),
                                "label": node.get("label"),
                                "kind": node.get("kind"),
                            }
                        )
            return {
                "kind": kind,
                "status": "ok",
                "graph_id": graph.get("graph_id"),
                "node_count": len(nodes) if isinstance(nodes, list) else 0,
                "node_preview": node_preview,
            }
    if kind == "deed" and isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str):
            return {"kind": kind, "status": "ok", "excerpt": _bounded_text(" ".join(text.split()), 320)}
    return {"kind": kind, "status": "ok"}


def _build_fix_skeleton(
    *,
    reason_code: str,
    action_type_raw: str,
    bootstrap_context: dict[str, object] | None = None,
) -> dict[str, object]:
    action = action_type_raw.strip().lower()
    args: dict[str, object] = {}
    required_fields: list[str] = []
    deed_ref = None
    if isinstance(bootstrap_context, dict):
        raw_deed_ref = bootstrap_context.get("deed_text_artifact_ref")
        if isinstance(raw_deed_ref, str) and raw_deed_ref.strip():
            deed_ref = raw_deed_ref.strip()
    if action == ActionType.OPEN_ARTIFACT.value:
        required_fields = ["artifact_ref | artifact_path | corpus_entry_ref"]
        args = {"artifact_ref": deed_ref or "<artifact-path-or-ref>"}
    elif action == ActionType.HYDRATE_DEED.value:
        required_fields = ["dossier_id | source_entry_ref"]
        args = {"dossier_id": "<dossier-id>"}
    elif action == ActionType.RETRIEVE_EVIDENCE.value:
        required_fields = ["query"]
        args = {"query": "<what you need to find>"}
    elif action in {ActionType.COMPILE.value, ActionType.JUDGE.value, ActionType.BUNDLE.value}:
        required_fields = ["ir_artifact_ref | updated_ir_artifact_ref | ir_artifact_path"]
        args = {"ir_artifact_ref": "<ir-artifact-ref>"}
    elif action == ActionType.DRAFT_IR.value:
        required_fields = [
            "dossier_id",
            "deed_text_artifact_ref | deed_artifact_ref | hydrated_deed_artifact_ref | graph",
        ]
        args = {
            "dossier_id": (
                str(bootstrap_context.get("dossier_id"))
                if isinstance(bootstrap_context, dict) and bootstrap_context.get("dossier_id") is not None
                else "<dossier-id>"
            ),
            "deed_text_artifact_ref": deed_ref or "<deed-text-artifact-ref>",
        }
    elif action == ActionType.DECLARE_DONE.value:
        required_fields = ["declare_done"]
        args = {}
    skeleton = {
        "kernel_step": {
            "action_type": action,
            "args": args,
            "idempotency_key": "<controller-computed>",
            "why": "corrective retry after refusal",
        },
        "required_fields": required_fields,
        "reason_code": reason_code,
    }
    return skeleton


def _autofill_known_args(
    *,
    action_type: ActionType,
    args: dict[str, object],
    bootstrap_context: dict[str, object],
    dashboard: dict[str, object],
) -> tuple[dict[str, object], set[str]]:
    filled: set[str] = set()
    updated = dict(args)
    deed_ref = _read_str(bootstrap_context.get("deed_text_artifact_ref"))
    dossier_id = _read_str(bootstrap_context.get("dossier_id"))
    source_entry_ref = _read_str(bootstrap_context.get("source_entry_ref"))
    latest_refs = _latest_refs_summary(dashboard)
    ir_ref = _read_str(latest_refs.get("ir_ref")) or _read_str(bootstrap_context.get("initial_ir_ref"))

    if action_type == ActionType.OPEN_ARTIFACT:
        has_any = any(_read_str(updated.get(k)) for k in ("artifact_ref", "artifact_path", "corpus_entry_ref"))
        if not has_any:
            if deed_ref:
                updated["artifact_ref"] = deed_ref
                filled.add("artifact_ref")
            elif source_entry_ref:
                updated["corpus_entry_ref"] = source_entry_ref
                filled.add("corpus_entry_ref")

    if action_type == ActionType.DRAFT_IR:
        if not _read_str(updated.get("dossier_id")) and dossier_id:
            updated["dossier_id"] = dossier_id
            filled.add("dossier_id")
        has_deed = any(
            _read_str(updated.get(k))
            for k in ("deed_text_artifact_ref", "deed_artifact_ref", "hydrated_deed_artifact_ref")
        )
        if not has_deed and "graph" not in updated and deed_ref:
            updated["deed_text_artifact_ref"] = deed_ref
            filled.add("deed_text_artifact_ref")

    if action_type in {ActionType.COMPILE, ActionType.JUDGE, ActionType.BUNDLE}:
        has_ir = any(_read_str(updated.get(k)) for k in ("ir_artifact_ref", "updated_ir_artifact_ref", "ir_artifact_path"))
        if not has_ir and ir_ref:
            updated["ir_artifact_ref"] = ir_ref
            filled.add("ir_artifact_ref")

    return updated, filled


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
    if not _should_emit_iteration_digest(outcome_kind=outcome_kind, executed_steps=executed_steps):
        return recent_digest_memory
    digest_seed = {
        "iter": iteration,
        "phase_hint": phase_hint,
        "context_inputs": context_packet.get("inputs", {}),
        "progress": (context_packet.get("progress") if isinstance(context_packet.get("progress"), dict) else {}),
        "proposal": {
            "action_type": proposal.action_type,
            "args": proposal.args,
            "why": proposal.why,
        },
        "outcome": {"kind": outcome_kind, **outcome_payload},
    }
    digest_payload: dict[str, object] | None = None
    if digest_client is not None:
        try:
            digest_result = digest_client.summarize_iteration_digest(payload=digest_seed, model="gpt-5-mini")
            candidate = digest_result.get("digest") if isinstance(digest_result, dict) else None
            if isinstance(candidate, dict):
                digest_payload = candidate
        except Exception:
            digest_payload = None
    if digest_payload is None:
        digest_payload = build_fallback_iteration_digest(seed=digest_seed)
    digest_ref, digest_excerpt = persist_iteration_digest(
        request_id=request_id,
        session_id=session_id,
        iteration=iteration,
        digest=digest_payload,
    )
    _log_controller_event(
        "iteration_digest_created",
        {
            "iteration": iteration,
            "digest_ref": digest_ref,
            "digest_excerpt": digest_excerpt,
            "result": digest_payload.get("result") if isinstance(digest_payload, dict) else None,
        },
    )
    updated = list(recent_digest_memory)
    updated.append({"iter": iteration, "digest_ref": digest_ref, "digest_excerpt": digest_excerpt})
    return updated[-8:]


def _should_emit_iteration_digest(*, outcome_kind: str, executed_steps: int) -> bool:
    if executed_steps == 0:
        return True
    if outcome_kind in {"controller_refusal", "kernel_refusal"}:
        return True
    if outcome_kind == "executed" and executed_steps % 3 == 0:
        return True
    return False


def _read_str(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    v = raw.strip()
    return v if v else None


def _compute_controller_idempotency_key(
    *,
    session_id: str,
    iteration: int,
    action_type: str,
    inputs: dict[str, object],
) -> str:
    normalized = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{session_id}|{iteration}|{action_type}|{normalized}".encode("utf-8")
    ).hexdigest()[:24]
    return f"ctl-{digest}"


def _update_refusal_streak(
    *,
    refusal_streak: int,
    previous_signature: str | None,
    reason_code: str,
    action_type: str,
    args: dict[str, object],
) -> tuple[int, str]:
    key_signature = _refusal_signature(reason_code=reason_code, action_type=action_type, args=args)
    if previous_signature == key_signature:
        return refusal_streak + 1, key_signature
    return 1, key_signature


def _refusal_signature(*, reason_code: str, action_type: str, args: dict[str, object]) -> str:
    arg_keys = sorted(args.keys())
    material = _material_change_fingerprint(action_type=action_type, args=args)
    return f"{reason_code}|{action_type}|{','.join(arg_keys)}|{material}"


def _material_change_fingerprint(*, action_type: str, args: dict[str, object]) -> str:
    action = action_type.strip().lower()
    if action == ActionType.RETRIEVE_EVIDENCE.value:
        query = _normalize_for_fingerprint(args.get("query"))
        if query:
            return f"query:{hashlib.sha256(query.encode('utf-8')).hexdigest()[:12]}"
    if action == ActionType.OPEN_ARTIFACT.value:
        ref_value = (
            _normalize_for_fingerprint(args.get("artifact_ref"))
            or _normalize_for_fingerprint(args.get("artifact_path"))
            or _normalize_for_fingerprint(args.get("corpus_entry_ref"))
        )
        if ref_value:
            return f"ref:{hashlib.sha256(ref_value.encode('utf-8')).hexdigest()[:12]}"
    return "static"


def _normalize_for_fingerprint(raw: object) -> str:
    if not isinstance(raw, str):
        return ""
    return " ".join(raw.split()).strip()[:256]


def _infer_phase_hint(dashboard: dict[str, object]) -> str:
    latest_refs = _latest_refs_summary(dashboard)
    claimability = dashboard.get("claimability")
    claimable_ready = False
    if isinstance(claimability, dict):
        claimable_ready = bool(claimability.get("claimable_ready"))
    if claimable_ready:
        return "declare_candidate"
    if not latest_refs.get("ir_ref"):
        return "author_ir"
    if not latest_refs.get("compile_ref") or not latest_refs.get("judge_ref"):
        return "verify"
    return "declare_candidate"


def _persist_run_summary(
    *,
    request_id: str,
    session_id: str,
    phase_hint: str,
    dashboard: dict[str, object],
    last_refusal: dict[str, object] | None,
    transcript: list[dict[str, object]],
) -> tuple[str, str]:
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


def _controller_proposal_log_payload(
    *,
    iteration: int,
    action_type: str,
    args: dict[str, object],
    why: str,
) -> dict[str, object]:
    return {
        "iteration": iteration,
        "action_type": action_type,
        "arg_keys": sorted(args.keys()),
        "args_material_fingerprint": _material_change_fingerprint(action_type=action_type, args=args),
        "why": _bounded_text(why, 160),
    }


def _controller_refusal_log_payload(
    *,
    iteration: int,
    reason_code: str,
    action_type: str,
    args: dict[str, object],
    missing_inputs: list[str],
    retryable: bool,
) -> dict[str, object]:
    return {
        "iteration": iteration,
        "reason_code": reason_code,
        "action_type": action_type,
        "arg_keys": sorted(args.keys()),
        "args_material_fingerprint": _material_change_fingerprint(action_type=action_type, args=args),
        "missing_inputs": missing_inputs[:8],
        "retryable": retryable,
    }


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
