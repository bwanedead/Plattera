"""Controller loop for driving the step-driven Agent Kernel."""

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


class NextStepLLMClient(Protocol):
    """LLM interface for proposing one controller step."""

    def propose_next_step(
        self,
        *,
        model: str,
        tools: list[ToolSpec],
        tool_choice_name: str | None,
        developer_message: str,
        user_message: str,
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
    _TRANSCRIPT_EVENT_HOOK.last_display_delta_fingerprint = None
    _TRANSCRIPT_EVENT_HOOK.recent_display_delta_fingerprints = []
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
    pending_refusal_repair: dict[str, object] | None = None
    last_refusal_action_type_raw: str | None = None
    parse_resync_last_iteration = False
    repeated_inspection_ref: str | None = None
    repeated_inspection_count = 0
    repeated_span_open_signature: str | None = None
    repeated_span_open_count = 0
    semantic_span_repair_signature: str | None = None
    semantic_span_repair_count = 0
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
        used_refusal_repair_prompt = pending_refusal_repair is not None
        if pending_refusal_repair is not None:
            proposal = _propose_refusal_repair_step(
                llm_client=llm_client,
                model=model,
                observation=context_packet,
                transcript=transcript,
                repair_request=pending_refusal_repair,
            )
            pending_refusal_repair = None
        else:
            proposal = _propose_next_step(
                llm_client=llm_client,
                model=model,
                observation=context_packet,
                transcript=transcript,
            )
        proposal_source = "llm_or_repair"
        if proposal is None:
            if not parse_resync_last_iteration:
                parse_resync = _build_parse_failure_resync_proposal(
                    iteration=iterations,
                    observation=context_packet,
                )
                if parse_resync is not None:
                    proposal = parse_resync
                    proposal_source = "controller_parse_resync"
                    parse_resync_last_iteration = True
                    _append_event(
                        transcript,
                        event_type="controller_parse_fail_resync",
                        detail=parse_resync.action_type,
                        payload={
                            "action_type": parse_resync.action_type,
                            "args": parse_resync.args,
                            "why": parse_resync.why,
                        },
                    )
                    _log_controller_event(
                        "controller_parse_fail_resync",
                        {
                            "iteration": iterations,
                            "action_type": parse_resync.action_type,
                            "arg_keys": sorted(parse_resync.args.keys()),
                            "args_material_fingerprint": _material_change_fingerprint(
                                action_type=parse_resync.action_type,
                                args=parse_resync.args,
                            ),
                            "why": _bounded_text(parse_resync.why, 160),
                        },
                    )
            if proposal is None:
                break
        else:
            parse_resync_last_iteration = False
        _append_event(
            transcript,
            event_type="agent_proposed_step",
            detail=proposal.action_type,
            payload={
                "action_type": proposal.action_type,
                "args": proposal.args,
                "why": proposal.why,
                "display_delta": proposal.display_delta,
                "proposal_source": proposal_source,
                "iteration_summary_excerpt": _run_summary_entry_excerpt(
                    _normalize_iteration_summary_payload(proposal.iteration_summary) or {"actual_observation": "missing"}
                )
                if proposal.iteration_summary is not None
                else None,
            },
        )
        _log_controller_event(
            "agent_proposed_step",
            _controller_proposal_log_payload(
                iteration=iterations,
                action_type=proposal.action_type,
                args=proposal.args,
                why=proposal.why,
                iteration_summary=proposal.iteration_summary,
                proposal_source=proposal_source,
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
                    iteration_summary=proposal.iteration_summary,
                ),
            )
            if not used_refusal_repair_prompt and refusal.retryable:
                pending_refusal_repair = _refusal_repair_request(
                    action_type_raw=proposal.action_type,
                    refusal=refusal,
                    bootstrap_context=bootstrap_context,
                    context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
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
                    iteration_summary=proposal.iteration_summary,
                ),
            )
            if not used_refusal_repair_prompt and refusal.retryable:
                pending_refusal_repair = _refusal_repair_request(
                    action_type_raw=action_type.value,
                    refusal=refusal,
                    bootstrap_context=bootstrap_context,
                    context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
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
            context_packet=context_packet,
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
                    iteration_summary=proposal.iteration_summary,
                ),
            )
            if not used_refusal_repair_prompt and payload_refusal.retryable:
                pending_refusal_repair = _refusal_repair_request(
                    action_type_raw=action_type.value,
                    refusal=payload_refusal,
                    bootstrap_context=bootstrap_context,
                    context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
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
                    iteration_summary=proposal.iteration_summary,
                ),
            )
            if not used_refusal_repair_prompt and refusal.retryable:
                pending_refusal_repair = _refusal_repair_request(
                    action_type_raw=action_type.value,
                    refusal=refusal,
                    bootstrap_context=bootstrap_context,
                    context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
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
            autofilled_declare_done = _autofill_declare_done_justification(
                dashboard=started.dashboard.model_dump(mode="json"),
            )
            if autofilled_declare_done is not None:
                proposal.declare_done = autofilled_declare_done

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
                    iteration_summary=proposal.iteration_summary,
                ),
            )
            if not used_refusal_repair_prompt and refusal.retryable:
                pending_refusal_repair = _refusal_repair_request(
                    action_type_raw=action_type.value,
                    refusal=refusal,
                    bootstrap_context=bootstrap_context,
                    context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
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
        inspection_refusal = _inspection_thrash_refusal(
            action_type=action_type,
            step_inputs=step_inputs,
            repeated_inspection_ref=repeated_inspection_ref,
            repeated_inspection_count=repeated_inspection_count,
        )
        if inspection_refusal is not None:
            refusal, repeat_ref = inspection_refusal
            last_refusal = refusal
            last_refusal_action_type_raw = action_type.value
            repeated_inspection_ref = repeat_ref
            repeated_inspection_count = (repeated_inspection_count + 1) if repeat_ref else 0
            dashboard_json = started.dashboard.model_dump(mode="json")
            next_action = _inspection_thrash_suggested_next_action(dashboard_json)
            progress_payload = {
                "latest_refs": _latest_refs_summary(dashboard_json),
                "gap_summary": _compact_gap_summary(dashboard_json.get("gap_summary")),
                "claimability": dashboard_json.get("claimability", {}),
            }
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={
                    "refusal": refusal.model_dump(mode="json"),
                    "fix": _build_fix_skeleton(
                        reason_code=refusal.reason_code,
                        action_type_raw=(next_action or action_type.value),
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=(next_action or action_type),
                        reason_code=refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                    "inspection_ref": repeat_ref,
                    "next_actions": _recommended_next_moves(progress_payload),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    args=step_inputs,
                    missing_inputs=refusal.missing_inputs,
                    retryable=refusal.retryable,
                    iteration_summary=proposal.iteration_summary,
                ),
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
        span_open_refusal = _span_open_thrash_refusal(
            action_type=action_type,
            step_inputs=step_inputs,
            repeated_signature=repeated_span_open_signature,
            repeated_count=repeated_span_open_count,
        )
        if span_open_refusal is not None:
            refusal, repeat_signature = span_open_refusal
            last_refusal = refusal
            last_refusal_action_type_raw = action_type.value
            repeated_span_open_signature = repeat_signature
            repeated_span_open_count = (repeated_span_open_count + 1) if repeat_signature else 0
            dashboard_json = started.dashboard.model_dump(mode="json")
            progress_payload = {
                "latest_refs": _latest_refs_summary(dashboard_json),
                "gap_summary": _compact_gap_summary(dashboard_json.get("gap_summary")),
                "claimability": dashboard_json.get("claimability", {}),
            }
            next_action = _span_open_thrash_suggested_next_action(dashboard_json)
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={
                    "refusal": refusal.model_dump(mode="json"),
                    "fix": _build_fix_skeleton(
                        reason_code=refusal.reason_code,
                        action_type_raw=(next_action or ActionType.DRAFT_IR).value,
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=(next_action or ActionType.DRAFT_IR),
                        reason_code=refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                    "next_actions": _recommended_next_moves(progress_payload),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    args=step_inputs,
                    missing_inputs=refusal.missing_inputs,
                    retryable=refusal.retryable,
                    iteration_summary=proposal.iteration_summary,
                ),
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
        semantic_span_refusal = _semantic_span_repair_thrash_refusal(
            action_type=action_type,
            context_packet=context_packet,
            repeated_signature=semantic_span_repair_signature,
            repeated_count=semantic_span_repair_count,
        )
        if semantic_span_refusal is not None:
            refusal, repeat_signature = semantic_span_refusal
            last_refusal = refusal
            last_refusal_action_type_raw = action_type.value
            semantic_span_repair_signature = repeat_signature
            semantic_span_repair_count = (semantic_span_repair_count + 1) if repeat_signature else 0
            dashboard_json = started.dashboard.model_dump(mode="json")
            progress_payload = {
                "latest_refs": _latest_refs_summary(dashboard_json),
                "gap_summary": _compact_gap_summary(dashboard_json.get("gap_summary")),
                "claimability": dashboard_json.get("claimability", {}),
            }
            next_action = _semantic_span_repair_thrash_suggested_next_action(dashboard_json)
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={
                    "refusal": refusal.model_dump(mode="json"),
                    "fix": _build_fix_skeleton(
                        reason_code=refusal.reason_code,
                        action_type_raw=(next_action or ActionType.DRAFT_IR).value,
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=(next_action or ActionType.DRAFT_IR),
                        reason_code=refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                    "next_actions": _recommended_next_moves(progress_payload),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    args=step_inputs,
                    missing_inputs=refusal.missing_inputs,
                    retryable=refusal.retryable,
                    iteration_summary=proposal.iteration_summary,
                ),
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
        dashboard_json = started.dashboard.model_dump(mode="json")
        redundant_step_refusal = _redundant_deterministic_step_refusal(
            action_type=action_type,
            dashboard=dashboard_json,
        )
        if redundant_step_refusal is not None:
            refusal, suggested_action = redundant_step_refusal
            last_refusal = refusal
            last_refusal_action_type_raw = action_type.value
            progress_payload = {
                "latest_refs": _latest_refs_summary(dashboard_json),
                "gap_summary": _compact_gap_summary(dashboard_json.get("gap_summary")),
                "claimability": dashboard_json.get("claimability", {}),
            }
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=refusal.reason_code,
                payload={
                    "refusal": refusal.model_dump(mode="json"),
                    "fix": _build_fix_skeleton(
                        reason_code=refusal.reason_code,
                        action_type_raw=(suggested_action or action_type).value,
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=(suggested_action or action_type),
                        reason_code=refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                    "next_actions": _recommended_next_moves(progress_payload),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=refusal.reason_code,
                    action_type=action_type.value,
                    args=step_inputs,
                    missing_inputs=refusal.missing_inputs,
                    retryable=refusal.retryable,
                    iteration_summary=proposal.iteration_summary,
                ),
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
            notes=_normalize_controller_notes(proposal.notes),
        )
        step_result = session_manager.step(step_request)
        if action_type == ActionType.OPEN_ARTIFACT:
            opened_ref = _read_str(step_inputs.get("artifact_ref")) or _read_str(step_inputs.get("artifact_path"))
            if opened_ref and opened_ref == repeated_inspection_ref:
                repeated_inspection_count += 1
            else:
                repeated_inspection_ref = opened_ref
                repeated_inspection_count = 1 if opened_ref else 0
        else:
            repeated_inspection_ref = None
            repeated_inspection_count = 0
        if action_type == ActionType.OPEN_TEXT_SPANS:
            span_sig = _open_text_spans_signature(step_inputs)
            if span_sig and span_sig == repeated_span_open_signature:
                repeated_span_open_count += 1
            else:
                repeated_span_open_signature = span_sig
                repeated_span_open_count = 1 if span_sig else 0
            semantic_sig = _semantic_span_repair_signature_for_context(context_packet)
            if semantic_sig and semantic_sig == semantic_span_repair_signature:
                semantic_span_repair_count += 1
            else:
                semantic_span_repair_signature = semantic_sig
                semantic_span_repair_count = 1 if semantic_sig else 0
        else:
            repeated_span_open_signature = None
            repeated_span_open_count = 0
            semantic_span_repair_signature = None
            semantic_span_repair_count = 0
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
        quality_refusal = _quality_gate_refusal_for_step_result(
            action_type=action_type,
            step_result=step_result,
            bootstrap_context=bootstrap_context,
        )
        if quality_refusal is not None:
            last_refusal = quality_refusal["refusal"]
            last_refusal_action_type_raw = action_type.value
            _append_event(
                transcript,
                event_type="controller_refusal",
                detail=last_refusal.reason_code,
                payload={
                    "refusal": last_refusal.model_dump(mode="json"),
                    "fix": _build_fix_skeleton(
                        reason_code=last_refusal.reason_code,
                        action_type_raw=action_type.value,
                        bootstrap_context=bootstrap_context,
                    ),
                    "how_to": action_how_to_guide(
                        action_type=action_type,
                        reason_code=last_refusal.reason_code,
                        context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
                    ),
                    "quality_gate": quality_refusal.get("quality_gate"),
                },
            )
            _log_controller_event(
                "controller_refusal",
                _controller_refusal_log_payload(
                    iteration=iterations,
                    reason_code=last_refusal.reason_code,
                    action_type=action_type.value,
                    args=step_inputs,
                    missing_inputs=last_refusal.missing_inputs,
                    retryable=last_refusal.retryable,
                    iteration_summary=proposal.iteration_summary,
                ),
            )
            if not used_refusal_repair_prompt and last_refusal.retryable:
                pending_refusal_repair = _refusal_repair_request(
                    action_type_raw=action_type.value,
                    refusal=last_refusal,
                    bootstrap_context=bootstrap_context,
                    context_inputs=context_packet.get("inputs", {}) if isinstance(context_packet, dict) else {},
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
        if step_result.execution_state == StepExecutionState.EXECUTED and quality_refusal is None:
            refusal_streak = 0
            previous_refusal_signature = None
            executed_steps += 1
        elif step_result.refusal is not None or quality_refusal is not None:
            active_refusal = step_result.refusal or (quality_refusal.get("refusal") if isinstance(quality_refusal, dict) else None)
            if not isinstance(active_refusal, KernelRefusal):
                active_refusal = None
            if active_refusal is None:
                active_refusal = KernelRefusal(reason_code="controller_quality_gate_failed", retryable=True)
            refusal_streak, previous_refusal_signature = _update_refusal_streak(
                refusal_streak=refusal_streak,
                previous_signature=previous_refusal_signature,
                reason_code=active_refusal.reason_code,
                action_type=action_type.value,
                args=step_inputs,
            )
            if refusal_streak >= 2:
                run_summary_ref, run_summary_excerpt = _persist_run_summary(
                    request_id=start_request.request_id,
                    session_id=session_id,
                    phase_hint=phase_hint,
                    dashboard=step_result.dashboard.model_dump(mode="json"),
                    last_refusal=active_refusal.model_dump(mode="json"),
                    transcript=transcript,
                )
            if refusal_streak >= _MAX_REFUSAL_STREAK:
                return _build_no_progress_result(
                    start_request=start_request,
                    session_id=session_id,
                    run_artifact_ref=started.run_artifact_ref,
                    dashboard=step_result.dashboard.model_dump(mode="json"),
                    transcript=transcript,
                    reason_code=active_refusal.reason_code,
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
                "controller_refusal" if quality_refusal is not None else "kernel_refusal" if step_result.refusal is not None else "executed"
                if step_result.execution_state == StepExecutionState.EXECUTED
                else "deduped"
            ),
            outcome_payload={
                "execution_state": step_result.execution_state.value,
                "reason_code": (
                    (quality_refusal["refusal"].reason_code if quality_refusal is not None else None)
                    or (step_result.refusal.reason_code if step_result.refusal is not None else None)
                    or (step_result.terminal.reason_code if step_result.terminal is not None else None)
                ),
                "missing_inputs": (
                    quality_refusal["refusal"].missing_inputs
                    if quality_refusal is not None
                    else (step_result.refusal.missing_inputs if step_result.refusal is not None else [])
                ),
                "step_record": step_result.step_record if isinstance(step_result.step_record, dict) else None,
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
    tool_menu = observation.get("tool_menu")
    tool_specs = action_tool_specs_for_menu(tool_menu if isinstance(tool_menu, list) else [])
    if not tool_specs:
        tool_specs = []
    first = llm_client.propose_next_step(
        model=model,
        tools=tool_specs,
        tool_choice_name=None,
        developer_message=build_developer_message(),
        user_message=build_user_message(context_packet=observation),
    )
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

    second = llm_client.propose_next_step(
        model=model,
        tools=tool_specs,
        tool_choice_name=None,
        developer_message=build_developer_message(),
        user_message=build_repair_user_message(parse_error=parse_error),
    )
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


def _propose_refusal_repair_step(
    *,
    llm_client: NextStepLLMClient,
    model: str,
    observation: dict[str, object],
    transcript: list[dict[str, object]],
    repair_request: dict[str, object],
) -> KernelStepProposal | None:
    tool_menu = observation.get("tool_menu")
    available_specs = action_tool_specs_for_menu(tool_menu if isinstance(tool_menu, list) else [])
    action_type_raw = _read_str(repair_request.get("action_type"))
    forced_specs = [spec for spec in available_specs if action_type_raw and spec.name == action_type_raw]
    tools = forced_specs or available_specs
    if not tools:
        return None
    minimal_example = repair_request.get("minimal_working_example")
    first = llm_client.propose_next_step(
        model=model,
        tools=tools,
        tool_choice_name=tools[0].name if len(tools) == 1 else action_type_raw,
        developer_message=build_developer_message(),
        user_message=build_refusal_repair_user_message(
            reason_code=str(repair_request.get("reason_code") or "unknown_refusal"),
            required_fields=[str(v) for v in (repair_request.get("required_fields") or []) if isinstance(v, str)],
            minimal_working_example=minimal_example if isinstance(minimal_example, dict) else None,
        ),
    )
    proposal, parse_error = _coerce_proposal(first)
    if proposal is not None:
        return proposal
    failure = _proposal_failure_payload(first, attempt="refusal_repair", parse_error=parse_error)
    _append_event(
        transcript,
        event_type="controller_parse_failed",
        detail="refusal_repair_parse_or_validation_failed",
        payload=failure,
    )
    _log_controller_event("controller_parse_failed", failure)
    return None


def _refusal_repair_request(
    *,
    action_type_raw: str,
    refusal: KernelRefusal,
    bootstrap_context: dict[str, object],
    context_inputs: dict[str, object],
 ) -> dict[str, object] | None:
    if coerce_action_type(action_type_raw) is None:
        return None
    resolved_action_type_raw = _override_refusal_repair_action_type(
        reason_code=refusal.reason_code,
        action_type_raw=action_type_raw,
        context_inputs=context_inputs,
    )
    how_to = action_how_to_guide(
        action_type=resolved_action_type_raw,
        reason_code=refusal.reason_code,
        context_inputs=context_inputs,
    )
    fix = _build_fix_skeleton(
        reason_code=refusal.reason_code,
        action_type_raw=resolved_action_type_raw,
        bootstrap_context=bootstrap_context,
    )
    kernel_step = fix.get("kernel_step")
    minimal = how_to.get("minimal_working_example")
    if isinstance(kernel_step, dict):
        ks_args = kernel_step.get("args")
        if isinstance(ks_args, dict):
            minimal = ks_args
    return {
        "action_type": resolved_action_type_raw,
        "reason_code": refusal.reason_code,
        "required_fields": how_to.get("required_fields") if isinstance(how_to.get("required_fields"), list) else [],
        "minimal_working_example": minimal if isinstance(minimal, dict) else None,
    }


def _override_refusal_repair_action_type(
    *,
    reason_code: str,
    action_type_raw: str,
    context_inputs: Mapping[str, object],
) -> str:
    normalized = str(reason_code or "").strip().lower()
    if normalized == "semantic_repair_span_loop_no_progress":
        return ActionType.DRAFT_IR.value
    if normalized == "repeated_span_open_no_progress":
        has_span_index = bool(_read_str(context_inputs.get("deed_span_index_ref")))
        return (ActionType.DRAFT_IR.value if has_span_index else ActionType.UPSERT_DEED_SPAN_INDEX.value)
    if normalized == "repeated_inspection_no_progress":
        return ActionType.DRAFT_IR.value
    return action_type_raw


def _coerce_proposal(raw: dict[str, object]) -> tuple[KernelStepProposal | None, str | None]:
    structured = raw.get("structured_data")
    if isinstance(structured, dict):
        try:
            validated = KernelStepProposal.model_validate(_sanitize_raw_proposal_payload(structured))
            return validated, None
        except Exception as exc:
            try:
                legacy = structured.get("proposal")
                if isinstance(legacy, dict):
                    validated = KernelStepProposal.model_validate(_sanitize_raw_proposal_payload(legacy))
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
            validated = KernelStepProposal.model_validate(_sanitize_raw_proposal_payload(parsed))
            return validated, None
        except Exception:
            legacy = parsed.get("proposal")
            if isinstance(legacy, dict):
                validated = KernelStepProposal.model_validate(_sanitize_raw_proposal_payload(legacy))
                return validated, None
            return None, "schema_validation_failed:ValidationError"
    except json.JSONDecodeError as exc:
        return None, f"json_parse_failed:{exc.msg}"
    except Exception as exc:
        return None, f"schema_validation_failed:{type(exc).__name__}"


def _sanitize_raw_proposal_payload(raw_payload: dict[str, object]) -> dict[str, object]:
    candidate = dict(raw_payload)
    candidate = _normalize_declare_done_candidate_payload(candidate)
    why_value = candidate.get("why")
    if isinstance(why_value, str) and len(why_value) > 500:
        candidate["why"] = why_value[:500]
    notes_value = candidate.get("notes")
    if isinstance(notes_value, str) and len(notes_value) > 2000:
        candidate["notes"] = notes_value[:2000]
    return candidate


def _normalize_declare_done_candidate_payload(candidate: dict[str, object]) -> dict[str, object]:
    action_type = str(candidate.get("action_type") or "").strip().lower()
    if action_type != ActionType.DECLARE_DONE.value:
        return candidate
    raw = candidate.get("declare_done")
    if not isinstance(raw, dict):
        return candidate
    normalized = dict(raw)

    raw_refs = normalized.get("artifact_refs")
    if isinstance(raw_refs, dict):
        alias_map = {
            "ir_artifact_ref": "ir_ref",
            "compile_artifact_ref": "compile_ref",
            "judge_artifact_ref": "judge_ref",
            "bundle_artifact_ref": "bundle_ref",
            "georeference_artifact_ref": "georef_ref",
            "georef_artifact_ref": "georef_ref",
            "validation_artifact_ref": "validate_ref",
            "validate_artifact_ref": "validate_ref",
            "render_artifact_ref": "render_ref",
        }
        refs_out: dict[str, object] = {}
        for key, value in raw_refs.items():
            k = str(key)
            canonical = alias_map.get(k, k)
            if canonical in {"ir_ref", "compile_ref", "judge_ref", "bundle_ref", "georef_ref", "validate_ref", "render_ref"}:
                refs_out[canonical] = value
        normalized["artifact_refs"] = refs_out

    raw_evidence = normalized.get("evidence_links")
    if isinstance(raw_evidence, list):
        fixed_links: list[dict[str, object]] = []
        for item in raw_evidence[:20]:
            if not isinstance(item, dict):
                continue
            source_raw = str(item.get("source") or "DEED").strip().upper()
            source = source_raw if source_raw in {"DEED", "RAG"} else "DEED"
            ref = item.get("ref")
            if ref is None:
                ref = item.get("artifact_ref")
            if ref is None:
                ref = item.get("reference")
            claim = item.get("claim")
            if claim is None:
                claim = item.get("description")
            if claim is None:
                claim = item.get("reason")
            ref_text = _read_str(ref)
            claim_text = _read_str(claim)
            if not ref_text or not claim_text:
                continue
            fixed_links.append({"source": source, "ref": ref_text, "claim": claim_text[:200]})
        normalized["evidence_links"] = fixed_links

    raw_deviations = normalized.get("accepted_deviations")
    if isinstance(raw_deviations, list):
        fixed_devs: list[dict[str, object]] = []
        for item in raw_deviations[:20]:
            if not isinstance(item, dict):
                continue
            kind = _read_str(item.get("kind")) or _read_str(item.get("type"))
            reason = _read_str(item.get("reason")) or _read_str(item.get("description"))
            if not kind or not reason:
                continue
            fixed_devs.append({"kind": kind[:64], "reason": reason[:200]})
        normalized["accepted_deviations"] = fixed_devs

    candidate["declare_done"] = normalized
    return candidate


def _normalize_controller_notes(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text[:500] if text else None
    try:
        rendered = json.dumps(_bound_payload(value), ensure_ascii=True, sort_keys=True)
    except Exception:
        rendered = str(value)
    rendered = rendered.strip()
    return rendered[:500] if rendered else None


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
        context["deed_fingerprint"] = _controller_deed_fingerprint(deed_text_full)
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


def _controller_deed_fingerprint(text: str) -> dict[str, object]:
    return {
        "sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        "length_chars": len(text),
    }


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
        "deed_fingerprint": bootstrap_context.get("deed_fingerprint"),
        "initial_ir_ref": bootstrap_context.get("initial_ir_ref"),
        "latest_ir_ref": latest_refs.get("ir_ref"),
        "deed_span_index_ref": latest_refs.get("deed_span_index_ref"),
    }
    memory_payload = _digest_memory_payload(recent_digest_memory)
    latest_span_memory = _latest_span_memory_from_step(last_step_result)
    if isinstance(latest_span_memory, dict):
        memory_payload.update({k: v for k, v in latest_span_memory.items() if v not in (None, [], "")})
    packet = {
        "session_id": session_id,
        "tool_menu": tool_menu,
        "ir_ops_menu": _ir_ops_menu_payload(),
        "inputs": packet_inputs,
        "progress": progress,
        "working_memory": {
            "phase_hint": phase_hint,
            "plan_bullets": _phase_plan_bullets(phase_hint),
            "anchor_templates": _anchor_templates_for_deed(bootstrap_context),
            "semantic_sanity_checklist": _semantic_sanity_checklist(),
        },
        "memory": memory_payload,
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
    artifacts_inline = packet.get("artifacts_inline")
    progress_payload = packet.get("progress")
    if isinstance(artifacts_inline, dict) and isinstance(progress_payload, dict):
        ir_hint = artifacts_inline.get("ir_hint")
        if isinstance(ir_hint, dict):
            progress_payload["ir_health"] = _ir_health_from_hint(ir_hint, latest_refs.get("ir_ref"))
        judge_hint = artifacts_inline.get("judge_hint")
        if isinstance(judge_hint, dict):
            progress_payload["judge_report_excerpt"] = _judge_excerpt_from_hint(judge_hint)
        georef_hint = artifacts_inline.get("georef_hint")
        validate_hint = artifacts_inline.get("validate_hint")
        if isinstance(georef_hint, dict) or isinstance(validate_hint, dict):
            progress_payload["map_sanity_excerpt"] = _map_sanity_excerpt_from_hints(
                georef_hint if isinstance(georef_hint, dict) else None,
                validate_hint if isinstance(validate_hint, dict) else None,
            )
        progress_payload["recommended_next"] = _recommended_next_moves(progress_payload)
    bounded = _bound_payload(packet, max_items=24)
    if isinstance(bounded, dict):
        deed_text_full = bootstrap_context.get("deed_text_full")
        inputs = bounded.get("inputs")
        if isinstance(inputs, dict) and isinstance(deed_text_full, str):
            inputs["deed_text_full"] = deed_text_full
    return bounded


def _latest_span_memory_from_step(last_step_result: KernelStepResult | None) -> dict[str, object] | None:
    if last_step_result is None or not isinstance(last_step_result.step_record, dict):
        return None
    out: dict[str, object] = {}
    outputs = last_step_result.step_record.get("outputs")
    if isinstance(outputs, dict):
        raw_ref = outputs.get("deed_span_index_ref")
        if isinstance(raw_ref, dict):
            artifact_path = raw_ref.get("artifact_path")
            if isinstance(artifact_path, str):
                out["deed_span_index_ref"] = artifact_path
    outputs_inline = last_step_result.step_record.get("outputs_inline")
    if isinstance(outputs_inline, dict):
        if isinstance(outputs_inline.get("span_catalog_excerpt"), list):
            out["deed_span_catalog_excerpt"] = outputs_inline.get("span_catalog_excerpt")
    return out or None


def _ir_ops_menu_payload() -> dict[str, object]:
    supported = sorted(get_supported_operations())
    unsupported = sorted(get_unsupported_operations())
    tempting = [name for name in unsupported if name in {"Union", "Intersection", "Difference", "Buffer", "Offset"}]
    return {
        "supported_compilable_ops": supported[:24],
        "registered_but_not_compilable_ops": tempting[:12],
        "authoring_rules": [
            "Do not invent op names.",
            "If an op is not compilable, encode deed meaning as direct geometry plus annotation metadata.",
        ],
    }


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
            "Compile, then judge for gap diagnosis after IR is non-stub.",
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


def _semantic_sanity_checklist() -> list[str]:
    return [
        "Prioritize faithful deed semantics over convenient but inaccurate graph structure; do not invent substitute geometry just to satisfy a gate.",
        "Before declare_done: ask if IR/map is a faithful semantic representation of the deed, not just structurally valid.",
        "If a deed-faithful detail is partially unsupported, preserve it explicitly in IR geometry/annotations/provenance and keep iterating instead of simplifying it away.",
        "Do not accept placeholder/sketch geometry as final mapped output.",
        "If deed ties POB to a corner/line and georef used centroid fallback, treat map as non-final and repair tie encoding.",
        "For partial deeds: map only fully stated parcels; keep incomplete parcels as explicit stubs/annotations, not fabricated geometry.",
        "If plotted shape looks implausible for the deed calls (e.g., wrong topology/triangle vs quadrilateral), reopen deed spans and revise IR.",
    ]


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
            "deed_span_index_ref": None,
            "deed_span_catalog_excerpt": None,
            "run_summary_log": [],
        }
    last = recent_digest_memory[-1]
    return {
        "last_digest_ref": last.get("digest_ref"),
        "last_digest_excerpt": last.get("digest_excerpt"),
        "recent_digests_excerpts": [d.get("digest_excerpt") for d in recent_digest_memory[-5:] if d.get("digest_excerpt")],
        "deed_span_index_ref": last.get("deed_span_index_ref"),
        "deed_span_catalog_excerpt": last.get("deed_span_catalog_excerpt"),
        "run_summary_log": [entry.get("run_summary_entry") for entry in recent_digest_memory if isinstance(entry.get("run_summary_entry"), dict)],
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
    georef_ref = latest_refs.get("georef_ref")
    if isinstance(georef_ref, str):
        hints["georef_hint"] = _safe_artifact_hint(georef_ref, kind="georef")
    validate_ref = latest_refs.get("validate_ref")
    if isinstance(validate_ref, str):
        hints["validate_hint"] = _safe_artifact_hint(validate_ref, kind="validate")
    render_ref = latest_refs.get("render_ref")
    if isinstance(render_ref, str):
        hints["render_hint"] = _safe_artifact_hint(render_ref, kind="render")
    return hints


def _safe_artifact_hint(path_value: str, *, kind: str) -> dict[str, object]:
    try:
        path = Path(path_value).resolve()
        allowed_roots = (
            agent_kernel_artifacts_root().resolve(),
            dossiers_feature_graphs_artifacts_root().resolve(),
        )
        if all(path != root and root not in path.parents for root in allowed_roots):
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
            warnings = report.get("warnings")
            if isinstance(gaps, list):
                top = []
                for gap in gaps[:3]:
                    if isinstance(gap, dict):
                        op_value = gap.get("operation") or gap.get("op_name") or gap.get("operation_name")
                        feature_value = gap.get("feature_id") or gap.get("node_id")
                        top.append(
                            {
                                "kind": gap.get("kind"),
                                "reason_code": gap.get("reason_code"),
                                "node_id": gap.get("node_id"),
                                "feature_id": feature_value,
                                "operation": op_value,
                                "severity": gap.get("severity"),
                                "message": _bounded_text(str(gap.get("message") or ""), 160),
                            }
                        )
                return {
                    "kind": kind,
                    "status": "ok",
                    "top_gaps": top,
                    "warnings": [str(w)[:160] for w in warnings[:3]] if isinstance(warnings, list) else [],
                }
    if kind == "ir" and isinstance(payload, dict):
        graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
        if isinstance(graph, dict):
            nodes = graph.get("nodes")
            node_preview = []
            has_structured_plss_anchor = False
            has_local_polygon_geometry = False
            parcel_audit = {"complete_region_count": 0, "partial_annotation_stub_count": 0}
            graph_meta = graph.get("metadata")
            if isinstance(graph_meta, dict) and _controller_ir_has_required_plss_anchor(graph_meta.get("plss_anchor")):
                has_structured_plss_anchor = True
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
                has_local_polygon_geometry = _controller_ir_has_local_polygon_geometry(nodes)
                parcel_audit = _controller_ir_parcel_audit(nodes)
                if not has_structured_plss_anchor:
                    for node in nodes:
                        if not isinstance(node, dict):
                            continue
                        if str(node.get("kind") or "").strip().lower() != "frame":
                            continue
                        metadata = node.get("metadata")
                        if isinstance(metadata, dict) and _controller_ir_has_required_plss_anchor(metadata.get("plss_anchor")):
                            has_structured_plss_anchor = True
                            break
            return {
                "kind": kind,
                "status": "ok",
                "graph_id": graph.get("graph_id"),
                "node_count": len(nodes) if isinstance(nodes, list) else 0,
                "node_preview": node_preview,
                "has_structured_plss_anchor": has_structured_plss_anchor,
                "has_local_polygon_geometry": has_local_polygon_geometry,
                "parcel_audit": parcel_audit,
            }
    if kind == "deed" and isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str):
            return {"kind": kind, "status": "ok", "excerpt": _bounded_text(" ".join(text.split()), 320)}
    if kind == "georef" and isinstance(payload, dict):
        bounds = payload.get("geographic_polygon", {}).get("bounds") if isinstance(payload.get("geographic_polygon"), dict) else None
        pob = payload.get("anchor_info", {}).get("pob_coordinates") if isinstance(payload.get("anchor_info"), dict) else None
        pob_method = payload.get("anchor_info", {}).get("pob_method") if isinstance(payload.get("anchor_info"), dict) else None
        coords = payload.get("geographic_polygon", {}).get("coordinates") if isinstance(payload.get("geographic_polygon"), dict) else None
        vertex_count = 0
        if isinstance(coords, list) and coords and isinstance(coords[0], list):
            vertex_count = len(coords[0])
        quality = payload.get("agent_kernel_quality") if isinstance(payload.get("agent_kernel_quality"), dict) else {}
        return {
            "kind": kind,
            "status": "ok",
            "success": bool(payload.get("success")),
            "bounds": bounds if isinstance(bounds, dict) else None,
            "pob": pob if isinstance(pob, dict) else None,
            "pob_method": pob_method if isinstance(pob_method, str) else None,
            "vertex_count": vertex_count,
            "plss_state": ((payload.get("plss_anchor") or {}).get("state") if isinstance(payload.get("plss_anchor"), dict) else None),
            "placeholder_geometry_detected": bool(isinstance(quality, dict) and quality.get("placeholder_geometry_detected") is True),
            "explicit_tie_reference_detected": bool(isinstance(quality, dict) and quality.get("explicit_tie_reference_detected") is True),
            "tie_to_corner_provided": bool(isinstance(quality, dict) and quality.get("tie_to_corner_provided") is True),
        }
    if kind == "validate" and isinstance(payload, dict):
        return {
            "kind": kind,
            "status": "ok",
            "passed": bool(payload.get("passed")),
            "reason_code": payload.get("reason_code"),
            "overall_accuracy": payload.get("overall_accuracy"),
            "top_issues": [str(v)[:160] for v in (payload.get("top_issues") or [])[:3]] if isinstance(payload.get("top_issues"), list) else [],
            "bounds": payload.get("bounds") if isinstance(payload.get("bounds"), dict) else None,
        }
    if kind == "render" and isinstance(payload, dict):
        svg_ref = payload.get("svg_artifact_ref")
        svg_path = svg_ref.get("artifact_path") if isinstance(svg_ref, dict) else None
        return {
            "kind": kind,
            "status": "ok",
            "width": payload.get("width"),
            "height": payload.get("height"),
            "vertex_count": payload.get("vertex_count"),
            "svg_artifact_path": svg_path if isinstance(svg_path, str) else None,
            "bounds": payload.get("bounds") if isinstance(payload.get("bounds"), dict) else None,
        }
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
            "graph",
            "deed_text_artifact_ref (recommended provenance)",
        ]
        args = {
            "dossier_id": (
                str(bootstrap_context.get("dossier_id"))
                if isinstance(bootstrap_context, dict) and bootstrap_context.get("dossier_id") is not None
                else "<dossier-id>"
            ),
            "deed_text_artifact_ref": deed_ref or "<deed-text-artifact-ref>",
            "graph": {
                "graph_id": "g_min_draft_001",
                "nodes": [{"id": "start_point", "kind": "point", "geometry": {"type": "Point", "coordinates": [0.0, 0.0]}}],
                "edges": [],
                "metadata": {"source": "deed"},
            },
        }
        if reason_code == "georef_missing_plss_anchor":
            required_fields.append("graph.metadata.plss_anchor OR FRAME.metadata.plss_anchor (canonical field name: plss_anchor)")
            args["graph"] = {
                "graph_id": "g_add_plss_anchor_fix_001",
                "nodes": [
                    {
                        "id": "local_frame",
                        "kind": "frame",
                        "metadata": {
                            "plss_anchor": {
                                "state": "Wyoming",
                                "township_number": 14,
                                "township_direction": "N",
                                "range_number": 75,
                                "range_direction": "W",
                                "section_number": 2,
                                "principal_meridian": "Sixth Principal Meridian",
                            }
                        },
                    }
                ],
                "edges": [],
                "metadata": {
                    "source": "deed",
                    "plss_anchor": {
                        "state": "Wyoming",
                        "township_number": 14,
                        "township_direction": "N",
                        "range_number": 75,
                        "range_direction": "W",
                        "section_number": 2,
                    },
                    "authoring_note": "Use canonical field name plss_anchor (NOT plss) for georeference compatibility.",
                },
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
    if action == ActionType.DECLARE_DONE.value:
        skeleton["kernel_step"]["declare_done"] = {
            "artifact_refs": {
                "ir_ref": "<latest ir ref>",
                "compile_ref": "<latest compile ref>",
                "judge_ref": "<latest judge ref>",
                "bundle_ref": "<latest bundle ref>",
            },
            "evidence_links": [],
            "accepted_deviations": [],
        }
    return skeleton


def _autofill_known_args(
    *,
    action_type: ActionType,
    args: dict[str, object],
    bootstrap_context: dict[str, object],
    dashboard: dict[str, object],
    context_packet: dict[str, object] | None = None,
) -> tuple[dict[str, object], set[str]]:
    filled: set[str] = set()
    updated = dict(args)
    deed_ref = _read_str(bootstrap_context.get("deed_text_artifact_ref"))
    deed_fingerprint = (
        bootstrap_context.get("deed_fingerprint")
        if isinstance(bootstrap_context.get("deed_fingerprint"), dict)
        else None
    )
    dossier_id = _read_str(bootstrap_context.get("dossier_id"))
    source_entry_ref = _read_str(bootstrap_context.get("source_entry_ref"))
    latest_refs = _latest_refs_summary(dashboard)
    ir_ref = _read_str(latest_refs.get("ir_ref")) or _read_str(bootstrap_context.get("initial_ir_ref"))
    memory = context_packet.get("memory") if isinstance(context_packet, dict) and isinstance(context_packet.get("memory"), dict) else {}
    deed_span_index_ref = _read_str(latest_refs.get("deed_span_index_ref")) or _read_str(memory.get("deed_span_index_ref"))

    if action_type == ActionType.OPEN_ARTIFACT:
        has_any = any(_read_str(updated.get(k)) for k in ("artifact_ref", "artifact_path", "corpus_entry_ref"))
        if not has_any:
            preferred_open_ref = (
                _read_str(latest_refs.get("judge_ref"))
                or _read_str(latest_refs.get("compile_ref"))
                or _read_str(latest_refs.get("ir_ref"))
                or deed_ref
            )
            if preferred_open_ref:
                updated["artifact_ref"] = preferred_open_ref
                filled.add("artifact_ref")
            elif source_entry_ref:
                updated["corpus_entry_ref"] = source_entry_ref
                filled.add("corpus_entry_ref")

    if action_type == ActionType.OPEN_TEXT_SPANS:
        if not _read_str(updated.get("deed_text_artifact_ref")) and deed_ref:
            updated["deed_text_artifact_ref"] = deed_ref
            filled.add("deed_text_artifact_ref")
        if isinstance(updated.get("span_ids"), list) and updated.get("span_ids"):
            if not _read_str(updated.get("deed_span_index_ref")) and deed_span_index_ref:
                updated["deed_span_index_ref"] = deed_span_index_ref
                filled.add("deed_span_index_ref")

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

    if action_type == ActionType.UPSERT_DEED_SPAN_INDEX:
        if not _read_str(updated.get("deed_text_artifact_ref")) and deed_ref:
            updated["deed_text_artifact_ref"] = deed_ref
            filled.add("deed_text_artifact_ref")
        if "deed_fingerprint" not in updated and isinstance(deed_fingerprint, dict):
            updated["deed_fingerprint"] = deed_fingerprint
            filled.add("deed_fingerprint")

    if action_type in {ActionType.COMPILE, ActionType.JUDGE, ActionType.BUNDLE}:
        has_ir = any(_read_str(updated.get(k)) for k in ("ir_artifact_ref", "updated_ir_artifact_ref", "ir_artifact_path"))
        if not has_ir and ir_ref:
            updated["ir_artifact_ref"] = ir_ref
            filled.add("ir_artifact_ref")

    if action_type == ActionType.GEOREFERENCE:
        if not _read_str(updated.get("bundle_artifact_ref")):
            bundle_ref = _read_str(latest_refs.get("bundle_ref"))
            if bundle_ref:
                updated["bundle_artifact_ref"] = bundle_ref
                filled.add("bundle_artifact_ref")
        has_any = any(_read_str(updated.get(k)) for k in ("bundle_artifact_ref", "ir_artifact_ref"))
        if not has_any and ir_ref:
            updated["ir_artifact_ref"] = ir_ref
            filled.add("ir_artifact_ref")

    if action_type == ActionType.VALIDATE:
        if not _read_str(updated.get("georef_artifact_ref")):
            georef_ref = _read_str(latest_refs.get("georef_ref"))
            if georef_ref:
                updated["georef_artifact_ref"] = georef_ref
                filled.add("georef_artifact_ref")
    if action_type == ActionType.RENDER:
        if not _read_str(updated.get("georef_artifact_ref")):
            georef_ref = _read_str(latest_refs.get("georef_ref"))
            if georef_ref:
                updated["georef_artifact_ref"] = georef_ref
                filled.add("georef_artifact_ref")

    return updated, filled


def _autofill_declare_done_justification(*, dashboard: dict[str, object]) -> DeclareDoneJustification | None:
    latest_refs = _latest_refs_summary(dashboard)
    if not isinstance(latest_refs, dict):
        return None
    if not any(_read_str(latest_refs.get(k)) for k in ("ir_ref", "compile_ref", "judge_ref", "bundle_ref")):
        return None
    payload = {
        "artifact_refs": {
            "ir_ref": _read_str(latest_refs.get("ir_ref")),
            "compile_ref": _read_str(latest_refs.get("compile_ref")),
            "judge_ref": _read_str(latest_refs.get("judge_ref")),
            "bundle_ref": _read_str(latest_refs.get("bundle_ref")),
            "georef_ref": _read_str(latest_refs.get("georef_ref")),
            "validate_ref": _read_str(latest_refs.get("validate_ref")),
            "render_ref": _read_str(latest_refs.get("render_ref")),
        },
        "evidence_links": [],
        "accepted_deviations": [],
    }
    try:
        return DeclareDoneJustification.model_validate(payload)
    except Exception:
        return None


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


def _ir_health_from_hint(ir_hint: dict[str, object], ir_ref: object) -> dict[str, object]:
    node_count = ir_hint.get("node_count")
    is_stub = bool(isinstance(node_count, int) and node_count == 0)
    has_structured_plss_anchor = bool(ir_hint.get("has_structured_plss_anchor") is True)
    has_local_polygon_geometry = bool(ir_hint.get("has_local_polygon_geometry") is True)
    parcel_audit = ir_hint.get("parcel_audit") if isinstance(ir_hint.get("parcel_audit"), dict) else {}
    return {
        "node_count": node_count if isinstance(node_count, int) else None,
        "edge_count": None,
        "is_stub": is_stub,
        "has_structured_plss_anchor": has_structured_plss_anchor,
        "has_local_polygon_geometry": has_local_polygon_geometry,
        "parcel_audit": parcel_audit,
        "last_ir_artifact_ref": ir_ref if isinstance(ir_ref, str) else None,
    }


def _controller_ir_parcel_audit(nodes: object) -> dict[str, int]:
    if not isinstance(nodes, list):
        return {"complete_region_count": 0, "partial_annotation_stub_count": 0}
    complete_regions = 0
    partial_annotation_stubs = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("kind") or "").strip().lower()
        label = str(node.get("label") or "").lower()
        meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        texts: list[str] = [label]
        for value in meta.values():
            if isinstance(value, str):
                texts.append(value.lower())
            elif isinstance(value, list):
                texts.extend(str(item).lower() for item in value if isinstance(item, str))
        joined = " ".join(texts)
        if kind == "region":
            complete_regions += 1
        if kind == "annotation" and any(tok in joined for tok in ("parcel", "stub", "truncated", "partial", "incomplete")):
            partial_annotation_stubs += 1
    return {
        "complete_region_count": complete_regions,
        "partial_annotation_stub_count": partial_annotation_stubs,
    }


def _controller_ir_has_local_polygon_geometry(nodes: object) -> bool:
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("kind") or "").strip().lower()
        geometry = node.get("geometry")
        if not isinstance(geometry, dict):
            continue
        gtype = str(geometry.get("type") or "").strip()
        if kind == "region" and gtype == "Polygon":
            coords = geometry.get("coordinates")
            if isinstance(coords, list) and coords and isinstance(coords[0], list) and len(coords[0]) >= 4:
                return True
        if kind == "curve" and gtype == "LineString":
            coords = geometry.get("coordinates")
            if (
                isinstance(coords, list)
                and len(coords) >= 4
                and isinstance(coords[0], list)
                and isinstance(coords[-1], list)
                and len(coords[0]) >= 2
                and len(coords[-1]) >= 2
                and coords[0][0] == coords[-1][0]
                and coords[0][1] == coords[-1][1]
            ):
                return True
    return False


def _controller_ir_has_required_plss_anchor(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required = (
        "state",
        "township_number",
        "township_direction",
        "range_number",
        "range_direction",
        "section_number",
    )
    return all(value.get(k) is not None for k in required)


def _judge_excerpt_from_hint(judge_hint: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {"top_gaps": [], "warnings": []}
    top_gaps = judge_hint.get("top_gaps")
    if isinstance(top_gaps, list):
        out["top_gaps"] = _bound_payload(top_gaps, max_items=4)
    warnings = judge_hint.get("warnings")
    if isinstance(warnings, list):
        out["warnings"] = [str(w)[:160] for w in warnings[:3]]
    return out


def _recommended_next_moves(progress_payload: dict[str, object]) -> list[str]:
    latest_refs = progress_payload.get("latest_refs")
    if not isinstance(latest_refs, dict):
        return []
    map_sanity = progress_payload.get("map_sanity_excerpt")
    if isinstance(map_sanity, dict):
        validate_top_issues = map_sanity.get("validate_top_issues")
        issues = [str(v).lower() for v in validate_top_issues] if isinstance(validate_top_issues, list) else []
        if any("section_centroid_anchor_fallback" in item for item in issues):
            return [
                "open_text_spans for the deed's POB tie language and encode an explicit tie_to_corner instead of centroid fallback",
                "re-georeference, validate, and render after replacing centroid fallback anchoring",
            ]
        if any("placeholder_geometry" in item for item in issues):
            return [
                "draft_ir update: replace placeholder parcel geometry with deed-faithful traverse/closed boundary before georeference",
                "re-compile, judge, bundle, georeference, validate, render",
            ]
        if any("unresolved_tie_to_corner" in item for item in issues):
            return [
                "open_text_spans for tie-to-corner language and encode tie_to_corner on the mapped parcel/POB metadata",
                "re-georeference, validate, and render after tie is explicit",
            ]
    ir_health = progress_payload.get("ir_health")
    if isinstance(ir_health, dict) and ir_health.get("is_stub") is True:
        return [
            "draft_ir with graph (non-empty FeatureGraph) before compile/judge",
            "use open_text_spans to extract deed calls, then encode nodes/op_expr",
        ]
    if latest_refs.get("ir_ref") and not latest_refs.get("compile_ref"):
        return ["run compile on latest ir_ref before more inspection", "then judge to refresh actionable gaps"]
    if latest_refs.get("compile_ref") and not latest_refs.get("judge_ref"):
        return ["run judge on latest compile/ir state to refresh gaps", "inspect judge repair_view/top gaps after judge"]
    gap_summary = progress_payload.get("gap_summary")
    if latest_refs.get("judge_ref") and isinstance(gap_summary, dict):
        counts = gap_summary.get("gap_counts_by_kind")
        total_gaps = 0
        if isinstance(counts, dict):
            for value in counts.values():
                try:
                    total_gaps += int(value)
                except Exception:
                    continue
        if total_gaps == 0:
            claimability = progress_payload.get("claimability")
            missing_claimability = (
                claimability.get("missing_claimability")
                if isinstance(claimability, dict) and isinstance(claimability.get("missing_claimability"), list)
                else []
            )
            ir_health = progress_payload.get("ir_health")
            has_structured_plss_anchor = bool(
                isinstance(ir_health, dict) and ir_health.get("has_structured_plss_anchor") is True
            )
            local_polygon_missing_known = bool(
                isinstance(ir_health, dict) and ir_health.get("has_local_polygon_geometry") is False
            )
            if latest_refs.get("bundle_ref") and latest_refs.get("georef_ref") and latest_refs.get("validate_ref"):
                if "has_render" in missing_claimability and not latest_refs.get("render_ref"):
                    return ["run render on latest georef_ref to produce a visual map preview", "then declare_done if claimability clears"]
                return ["declare_done with justification if semantics are satisfied"]
            if (
                latest_refs.get("bundle_ref")
                and ("has_georef" in missing_claimability)
                and local_polygon_missing_known
            ):
                return [
                    "draft_ir update: add explicit local parcel polygon geometry (region Polygon or closed LineString ring)",
                    "re-bundle, then georeference and validate",
                ]
            if (
                latest_refs.get("bundle_ref")
                and ("has_georef" in missing_claimability)
                and not has_structured_plss_anchor
            ):
                return [
                    "draft_ir update: add structured plss_anchor to FRAME.metadata.plss_anchor or graph.metadata.plss_anchor",
                    "re-bundle, then georeference and validate",
                ]
            if latest_refs.get("bundle_ref") and ("has_georef" in missing_claimability or "validation_passed" in missing_claimability):
                return ["run georeference on latest bundle, then validate", "declare_done only after georef/validate claimability clears"]
            if latest_refs.get("bundle_ref") and not latest_refs.get("georef_ref"):
                return ["run georeference on latest bundle", "then validate and consider declare_done"]
            if latest_refs.get("georef_ref") and not latest_refs.get("validate_ref"):
                return ["run validate on latest georef_ref", "then consider declare_done if claimability clears"]
            if latest_refs.get("georef_ref") and latest_refs.get("validate_ref") and ("has_render" in missing_claimability):
                return ["run render on latest georef_ref", "then consider declare_done if claimability clears"]
            if latest_refs.get("bundle_ref"):
                return ["declare_done with justification if semantics are satisfied"]
            return ["bundle latest graph artifacts, then georeference/validate if required"]
    if latest_refs.get("judge_ref"):
        return ["inspect judge_report_excerpt/top gaps, then revise IR graph", "compile and judge immediately after each IR change"]
    if latest_refs.get("ir_ref"):
        return ["run compile then judge on latest ir_ref"]
    return ["draft_ir with graph (non-empty FeatureGraph)"]


def _map_sanity_excerpt_from_hints(
    georef_hint: dict[str, object] | None,
    validate_hint: dict[str, object] | None,
) -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(georef_hint, dict):
        for key in (
            "success",
            "bounds",
            "pob",
            "pob_method",
            "vertex_count",
            "plss_state",
            "placeholder_geometry_detected",
            "explicit_tie_reference_detected",
            "tie_to_corner_provided",
        ):
            if key in georef_hint:
                out[key] = georef_hint.get(key)
    if isinstance(validate_hint, dict):
        for key in ("passed", "reason_code", "overall_accuracy", "top_issues"):
            if key in validate_hint:
                out[f"validate_{key}" if key not in {"passed", "top_issues"} else ("validate_passed" if key == "passed" else "validate_top_issues")] = validate_hint.get(key)
    return out


def _inspection_thrash_refusal(
    *,
    action_type: ActionType,
    step_inputs: dict[str, object],
    repeated_inspection_ref: str | None,
    repeated_inspection_count: int,
) -> tuple[KernelRefusal, str] | None:
    if action_type != ActionType.OPEN_ARTIFACT:
        return None
    artifact_ref = _read_str(step_inputs.get("artifact_ref")) or _read_str(step_inputs.get("artifact_path"))
    if not artifact_ref:
        return None
    if artifact_ref != repeated_inspection_ref:
        return None
    if repeated_inspection_count < 1:
        return None
    return (
        KernelRefusal(
            reason_code="repeated_inspection_no_progress",
            missing_inputs=[],
            retryable=True,
        ),
        artifact_ref,
    )


def _span_open_thrash_refusal(
    *,
    action_type: ActionType,
    step_inputs: dict[str, object],
    repeated_signature: str | None,
    repeated_count: int,
) -> tuple[KernelRefusal, str] | None:
    if action_type != ActionType.OPEN_TEXT_SPANS:
        return None
    signature = _open_text_spans_signature(step_inputs)
    if not signature:
        return None
    if signature != repeated_signature:
        return None
    if repeated_count < 1:
        return None
    return (
        KernelRefusal(
            reason_code="repeated_span_open_no_progress",
            missing_inputs=[],
            retryable=True,
        ),
        signature,
    )


def _semantic_span_repair_signature_for_context(context_packet: Mapping[str, object]) -> str | None:
    progress = context_packet.get("progress")
    if not isinstance(progress, Mapping):
        return None
    latest_refs = progress.get("latest_refs")
    if not isinstance(latest_refs, Mapping):
        return None
    ir_ref = _read_str(latest_refs.get("ir_ref"))
    validate_ref = _read_str(latest_refs.get("validate_ref"))
    if not ir_ref or not validate_ref:
        return None
    map_sanity = progress.get("map_sanity_excerpt")
    if not isinstance(map_sanity, Mapping):
        return None
    raw_issues = map_sanity.get("validate_top_issues")
    if not isinstance(raw_issues, list):
        return None
    issues = sorted(
        {
            str(item).strip().lower()
            for item in raw_issues
            if isinstance(item, str)
            and (
                "section_centroid_anchor_fallback" in item.lower()
                or "unresolved_tie_to_corner" in item.lower()
            )
        }
    )
    if not issues:
        return None
    deed_span_index_ref = _read_str(latest_refs.get("deed_span_index_ref"))
    payload = {"ir_ref": ir_ref, "validate_ref": validate_ref, "issues": issues, "deed_span_index_ref": deed_span_index_ref}
    try:
        return json.dumps(payload, sort_keys=True, ensure_ascii=True)
    except Exception:
        return str(payload)


def _semantic_span_repair_thrash_refusal(
    *,
    action_type: ActionType,
    context_packet: Mapping[str, object],
    repeated_signature: str | None,
    repeated_count: int,
) -> tuple[KernelRefusal, str] | None:
    if action_type != ActionType.OPEN_TEXT_SPANS:
        return None
    signature = _semantic_span_repair_signature_for_context(context_packet)
    if not signature or signature != repeated_signature:
        return None
    if repeated_count < 2:
        return None
    return (
        KernelRefusal(
            reason_code="semantic_repair_span_loop_no_progress",
            missing_inputs=[],
            retryable=True,
        ),
        signature,
    )


def _open_text_spans_signature(step_inputs: Mapping[str, object]) -> str | None:
    sig_payload: dict[str, object] = {}
    for key in (
        "deed_text_artifact_ref",
        "artifact_ref",
        "deed_span_index_ref",
        "start_char",
        "end_char",
        "max_chars",
        "span_ids",
        "spans",
        "anchors",
    ):
        if key in step_inputs:
            sig_payload[key] = step_inputs.get(key)
    if not sig_payload:
        return None
    try:
        return json.dumps(sig_payload, sort_keys=True, ensure_ascii=True)
    except Exception:
        return str(sig_payload)


def _redundant_deterministic_step_refusal(
    *,
    action_type: ActionType,
    dashboard: dict[str, object],
) -> tuple[KernelRefusal, ActionType | None] | None:
    latest_refs = _latest_refs_summary(dashboard)
    if action_type == ActionType.COMPILE and latest_refs.get("compile_ref"):
        next_action = ActionType.JUDGE if not latest_refs.get("judge_ref") else None
        return (
            KernelRefusal(
                reason_code="compile_already_current",
                missing_inputs=[],
                retryable=True,
            ),
            next_action,
        )
    if action_type == ActionType.JUDGE and latest_refs.get("judge_ref"):
        next_action = ActionType.BUNDLE if not latest_refs.get("bundle_ref") else None
        return (
            KernelRefusal(
                reason_code="judge_already_current",
                missing_inputs=[],
                retryable=True,
            ),
            next_action,
        )
    return None


def _inspection_thrash_suggested_next_action(dashboard: dict[str, object]) -> ActionType | None:
    latest_refs = _latest_refs_summary(dashboard)
    if latest_refs.get("ir_ref") and not latest_refs.get("compile_ref"):
        return ActionType.COMPILE
    if latest_refs.get("compile_ref") and not latest_refs.get("judge_ref"):
        return ActionType.JUDGE
    if latest_refs.get("judge_ref"):
        return ActionType.DRAFT_IR
    return None


def _semantic_span_repair_thrash_suggested_next_action(dashboard: dict[str, object]) -> ActionType | None:
    latest_refs = _latest_refs_summary(dashboard)
    if not latest_refs.get("deed_span_index_ref"):
        return ActionType.UPSERT_DEED_SPAN_INDEX
    return ActionType.DRAFT_IR


def _span_open_thrash_suggested_next_action(dashboard: dict[str, object]) -> ActionType | None:
    latest_refs = _latest_refs_summary(dashboard)
    if not latest_refs.get("deed_span_index_ref"):
        return ActionType.UPSERT_DEED_SPAN_INDEX
    if latest_refs.get("ir_ref"):
        return ActionType.DRAFT_IR
    return ActionType.OPEN_ARTIFACT


def _build_parse_failure_resync_proposal(
    *,
    iteration: int,
    observation: dict[str, object],
) -> KernelStepProposal | None:
    progress = observation.get("progress")
    if not isinstance(progress, dict):
        return None
    latest_refs = progress.get("latest_refs")
    if not isinstance(latest_refs, dict):
        return None
    artifact_ref = None
    for key in ("judge_ref", "compile_ref", "ir_ref"):
        candidate = latest_refs.get(key)
        if isinstance(candidate, str) and candidate.strip():
            artifact_ref = candidate.strip()
            break
    if artifact_ref is None:
        return None
    return KernelStepProposal(
        action_type=ActionType.OPEN_ARTIFACT.value,
        args={"artifact_ref": artifact_ref},
        idempotency_key=f"controller-parse-resync-{iteration}",
        why="controller parse-fail resync: inspect latest artifact for actionable feedback",
        iteration_summary={
            "action": "propose:open_artifact; observed_last:parse_failed",
            "actual_observation": "parse_failed(controller_parse_failed); need deterministic resync",
            "expected_observation": "next iteration will have a bounded artifact repair view or summary",
            "next_move": {"action_type": "open_artifact", "why": "recover context after parse failure"},
            "confidence": "low",
        },
    )


def _anchor_templates_for_deed(bootstrap_context: dict[str, object]) -> list[dict[str, str]]:
    if not isinstance(bootstrap_context.get("deed_text_excerpt"), str):
        return []
    return [
        {"label": "metes_bounds_calls", "start_anchor": "BEGINNING AT", "end_anchor": "POINT OF BEGINNING"},
        {"label": "metes_bounds_calls_alt", "start_anchor": "Beginning at", "end_anchor": "point of beginning"},
        {"label": "exception_clause", "start_anchor": "EXCEPTING", "end_anchor": "TOGETHER WITH"},
    ]


def _quality_gate_refusal_for_step_result(
    *,
    action_type: ActionType,
    step_result: KernelStepResult,
    bootstrap_context: dict[str, object],
) -> dict[str, object] | None:
    if action_type != ActionType.DRAFT_IR:
        return None
    if step_result.execution_state != StepExecutionState.EXECUTED or step_result.refusal is not None:
        return None
    latest_refs = _latest_refs_summary(step_result.dashboard.model_dump(mode="json"))
    ir_ref = latest_refs.get("ir_ref")
    if not isinstance(ir_ref, str) or not ir_ref:
        return None
    ir_hint = _safe_artifact_hint(ir_ref, kind="ir")
    if not isinstance(ir_hint, dict):
        return None
    node_count = ir_hint.get("node_count")
    if not isinstance(node_count, int) or node_count > 0:
        return None
    refusal = KernelRefusal(
        reason_code="draft_ir_graph_empty",
        missing_inputs=["graph.nodes[0]"],
        retryable=True,
    )
    return {
        "refusal": refusal,
        "quality_gate": {
            "kind": "ir_health",
            "reason_code": "draft_ir_graph_empty",
            "ir_ref": ir_ref,
            "ir_hint": _bound_payload(ir_hint, max_items=8),
            "message": "draft_ir produced an empty graph; next attempt must include graph with at least one node",
        },
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
