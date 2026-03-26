"""Controller loop implementation module."""

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
from typing import Any, Callable, Mapping, Protocol, TypeVar
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

ControllerRunResultT = TypeVar("ControllerRunResultT")

from .controller_bootstrap import _bootstrap_deed_span_index_from_transcript_seeds, _build_bootstrap_context
from .controller_context import _build_context_packet, _compact_gap_summary
from .controller_guardrails import (
    _build_parse_failure_resync_proposal,
    _compute_controller_idempotency_key,
    _infer_phase_hint,
    _inspection_thrash_refusal,
    _material_change_fingerprint,
    _open_text_spans_signature,
    _quality_gate_refusal_for_step_result,
    _read_str,
    _redundant_deterministic_step_refusal,
    _semantic_span_repair_signature_for_context,
    _semantic_span_repair_thrash_refusal,
    _span_open_thrash_refusal,
    _update_refusal_streak,
)
from .controller_proposals import (
    _autofill_declare_done_justification,
    _autofill_known_args,
    _build_fix_skeleton,
    _normalize_controller_notes,
    _normalize_declare_done_candidate_payload,
    _propose_next_step,
    _propose_refusal_repair_step,
    _refusal_repair_request,
    _sanitize_raw_proposal_payload,
    _validate_controller_inputs,
)
from .controller_summary import (
    _bound_run_summary_memory,
    _build_no_progress_result,
    _build_run_summary_entry,
    _fallback_iteration_summary,
    _finalize_docket_summary,
    _maybe_create_iteration_digest,
    _normalize_docket_dict,
    _normalize_docket_state_delta,
    _normalize_iteration_summary_payload,
    _persist_run_summary,
    _run_summary_entry_excerpt,
)
from .controller_runtime_step_prep import _prepare_step_request
from .controller_transcript import (
    _TRANSCRIPT_EVENT_HOOK,
    _append_event,
    _bounded_text,
    _controller_proposal_log_payload,
    _controller_refusal_log_payload,
    _latest_refs_summary,
    _log_controller_event,
    _persist_controller_transcript,
    _proposal_failure_payload,
    _sanitize_and_dedupe_display_delta,
    _synth_controller_refusal_display_delta,
    _synth_kernel_step_result_display_delta,
)

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
    handoff_posture: dict[str, object] | None = None


def _run_controller_loop_impl(
    *,
    session_manager: KernelSessionManager,
    llm_client: NextStepLLMClient,
    start_request: KernelSessionStartRequest,
    model: str = "gpt-5-mini",
    max_iterations: int = 20,
    digest_client: IterationDigestClient | None = None,
    controller_run_result_cls: type[ControllerRunResultT],
    controller_loop_error_cls: type[Exception],
) -> ControllerRunResultT:
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
        return controller_run_result_cls(
            terminal=terminal,
            last_dashboard=started.dashboard.model_dump(mode="json") if started.dashboard is not None else {},
            transcript_artifact_ref=transcript_ref,
            session_id=session_id,
            run_artifact_ref=started.run_artifact_ref,
            iterations=0,
        )
    if started.dashboard is None or session_id is None:
        raise controller_loop_error_cls("kernel_start_session_missing_dashboard_or_session")

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
    seed_bootstrap_step = _bootstrap_deed_span_index_from_transcript_seeds(
        session_manager=session_manager,
        session_id=session_id,
        request_id=start_request.request_id,
        bootstrap_context=bootstrap_context,
    )
    if seed_bootstrap_step is not None:
        started.dashboard = seed_bootstrap_step.dashboard
        _append_event(
            transcript,
            event_type="bootstrap_span_seeds_materialized",
            detail=seed_bootstrap_step.execution_state.value,
            payload={
                "execution_state": seed_bootstrap_step.execution_state.value,
                "reason_code": (
                    seed_bootstrap_step.refusal.reason_code
                    if seed_bootstrap_step.refusal is not None
                    else None
                ),
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
                run_link_id=start_request.request_id,
                mission_objective=str(start_request.objective or ""),
            )
            pending_refusal_repair = None
        else:
            proposal = _propose_next_step(
                llm_client=llm_client,
                model=model,
                observation=context_packet,
                transcript=transcript,
                run_link_id=start_request.request_id,
                mission_objective=str(start_request.objective or ""),
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

        prep = _prepare_step_request(
            session_id=session_id,
            start_request=start_request,
            started=started,
            action_type=action_type,
            proposal=proposal,
            context_packet=context_packet,
            transcript=transcript,
            bootstrap_context=bootstrap_context,
            iterations=iterations,
            phase_hint=phase_hint,
            used_refusal_repair_prompt=used_refusal_repair_prompt,
            digest_client=digest_client,
            pending_refusal_repair=pending_refusal_repair,
            refusal_streak=refusal_streak,
            previous_refusal_signature=previous_refusal_signature,
            run_summary_ref=run_summary_ref,
            run_summary_excerpt=run_summary_excerpt,
            recent_digest_memory=recent_digest_memory,
            last_refusal=last_refusal,
            last_refusal_action_type_raw=last_refusal_action_type_raw,
            repeated_inspection_ref=repeated_inspection_ref,
            repeated_inspection_count=repeated_inspection_count,
            repeated_span_open_signature=repeated_span_open_signature,
            repeated_span_open_count=repeated_span_open_count,
            semantic_span_repair_signature=semantic_span_repair_signature,
            semantic_span_repair_count=semantic_span_repair_count,
        )
        last_refusal = prep.last_refusal
        last_refusal_action_type_raw = prep.last_refusal_action_type_raw
        pending_refusal_repair = prep.pending_refusal_repair
        refusal_streak = prep.refusal_streak
        previous_refusal_signature = prep.previous_refusal_signature
        run_summary_ref = prep.run_summary_ref
        run_summary_excerpt = prep.run_summary_excerpt
        recent_digest_memory = prep.recent_digest_memory
        repeated_inspection_ref = prep.repeated_inspection_ref
        repeated_inspection_count = prep.repeated_inspection_count
        repeated_span_open_signature = prep.repeated_span_open_signature
        repeated_span_open_count = prep.repeated_span_open_count
        semantic_span_repair_signature = prep.semantic_span_repair_signature
        semantic_span_repair_count = prep.semantic_span_repair_count
        if prep.terminal_result is not None:
            return prep.terminal_result
        if prep.continue_loop:
            continue
        if prep.step_request is None or prep.step_inputs is None:
            raise controller_loop_error_cls("controller_step_preparation_missing_step_request")
        step_request = prep.step_request
        step_inputs = prep.step_inputs
        computed_idempotency_key = prep.computed_idempotency_key or step_request.idempotency_key
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
            return controller_run_result_cls(
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
    return controller_run_result_cls(
        terminal=terminal,
        last_dashboard=started.dashboard.model_dump(mode="json"),
        transcript_artifact_ref=transcript_ref,
        session_id=session_id,
        run_artifact_ref=started.run_artifact_ref,
        iterations=iterations,
    )
