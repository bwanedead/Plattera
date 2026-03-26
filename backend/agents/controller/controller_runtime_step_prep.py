"""Pre-step preparation helpers for controller runtime iterations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent_kernel.models import (
    ActionType,
    KernelRefusal,
    KernelSessionStartRequest,
    KernelSessionStartResult,
    KernelStepRequest,
)

from .contracts import KernelStepProposal, validate_action_args
from .controller_context import _compact_gap_summary
from .controller_guardrails import (
    _compute_controller_idempotency_key,
    _inspection_thrash_refusal,
    _open_text_spans_signature,
    _read_str,
    _progress_state_labels,
    _redundant_deterministic_step_refusal,
    _semantic_span_repair_thrash_refusal,
    _span_open_thrash_refusal,
    _update_refusal_streak,
)
from .controller_proposals import (
    _autofill_declare_done_justification,
    _autofill_known_args,
    _build_fix_skeleton,
    _normalize_controller_notes,
    _refusal_repair_request,
    _validate_controller_inputs,
)
from .controller_summary import _build_no_progress_result, _maybe_create_iteration_digest, _persist_run_summary
from .controller_transcript import (
    _append_event,
    _controller_refusal_log_payload,
    _latest_refs_summary,
    _log_controller_event,
)
from .retrieval_intents import map_retrieval_intent_to_inputs


@dataclass(frozen=True)
class StepPreparationResult:
    last_refusal: KernelRefusal | None
    last_refusal_action_type_raw: str | None
    pending_refusal_repair: dict[str, object] | None
    refusal_streak: int
    previous_refusal_signature: str | None
    run_summary_ref: str | None
    run_summary_excerpt: str | None
    recent_digest_memory: list[dict[str, object]]
    repeated_inspection_ref: str | None
    repeated_inspection_count: int
    repeated_span_open_signature: str | None
    repeated_span_open_count: int
    semantic_span_repair_signature: str | None
    semantic_span_repair_count: int
    computed_idempotency_key: str | None = None
    step_request: KernelStepRequest | None = None
    step_inputs: dict[str, Any] | None = None
    continue_loop: bool = False
    terminal_result: object | None = None


def _prepare_step_request(
    *,
    session_id: str,
    start_request: KernelSessionStartRequest,
    started: KernelSessionStartResult,
    action_type: ActionType,
    proposal: KernelStepProposal,
    context_packet: Mapping[str, Any],
    transcript: list[dict[str, object]],
    bootstrap_context: Mapping[str, Any],
    iterations: int,
    phase_hint: str,
    used_refusal_repair_prompt: bool,
    digest_client: Any | None,
    pending_refusal_repair: dict[str, object] | None,
    refusal_streak: int,
    previous_refusal_signature: str | None,
    run_summary_ref: str | None,
    run_summary_excerpt: str | None,
    recent_digest_memory: list[dict[str, object]],
    last_refusal: KernelRefusal | None,
    last_refusal_action_type_raw: str | None,
    repeated_inspection_ref: str | None,
    repeated_inspection_count: int,
    repeated_span_open_signature: str | None,
    repeated_span_open_count: int,
    semantic_span_repair_signature: str | None,
    semantic_span_repair_count: int,
) -> StepPreparationResult:
    def _result(
        *,
        step_request: KernelStepRequest | None = None,
        step_inputs: dict[str, Any] | None = None,
        continue_loop: bool = False,
        terminal_result: object | None = None,
    ) -> StepPreparationResult:
        return StepPreparationResult(
            last_refusal=last_refusal,
            last_refusal_action_type_raw=last_refusal_action_type_raw,
            pending_refusal_repair=pending_refusal_repair,
            refusal_streak=refusal_streak,
            previous_refusal_signature=previous_refusal_signature,
            run_summary_ref=run_summary_ref,
            run_summary_excerpt=run_summary_excerpt,
            recent_digest_memory=recent_digest_memory,
            repeated_inspection_ref=repeated_inspection_ref,
            repeated_inspection_count=repeated_inspection_count,
            repeated_span_open_signature=repeated_span_open_signature,
            repeated_span_open_count=repeated_span_open_count,
            semantic_span_repair_signature=semantic_span_repair_signature,
            semantic_span_repair_count=semantic_span_repair_count,
            computed_idempotency_key=None,
            step_request=step_request,
            step_inputs=step_inputs,
            continue_loop=continue_loop,
            terminal_result=terminal_result,
        )

    def _handle_controller_refusal(
        *,
        refusal: KernelRefusal,
        args_for_log: Mapping[str, Any],
        args_for_streak: Mapping[str, Any] | None = None,
        payload_extra: dict[str, object] | None = None,
        update_streak: bool = False,
        allow_repair_request: bool = False,
    ) -> StepPreparationResult:
        nonlocal last_refusal
        nonlocal last_refusal_action_type_raw
        nonlocal pending_refusal_repair
        nonlocal refusal_streak
        nonlocal previous_refusal_signature
        nonlocal run_summary_ref
        nonlocal run_summary_excerpt
        nonlocal recent_digest_memory

        last_refusal = refusal
        last_refusal_action_type_raw = action_type.value
        payload = {
            "refusal": refusal.model_dump(mode="json"),
            "fix": _build_fix_skeleton(
                reason_code=refusal.reason_code,
                action_type_raw=action_type.value,
                bootstrap_context=bootstrap_context,
            ),
        }
        if payload_extra:
            payload.update(payload_extra)
        _append_event(
            transcript,
            event_type="controller_refusal",
            detail=refusal.reason_code,
            payload=payload,
        )
        _log_controller_event(
            "controller_refusal",
            _controller_refusal_log_payload(
                iteration=iterations,
                reason_code=refusal.reason_code,
                action_type=action_type.value,
                args=dict(args_for_log),
                missing_inputs=refusal.missing_inputs,
                retryable=refusal.retryable,
                iteration_summary=proposal.iteration_summary,
            ),
        )
        if update_streak:
            if allow_repair_request and not used_refusal_repair_prompt and refusal.retryable:
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
                args=dict(args_for_streak or args_for_log),
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
            if refusal_streak >= 3:
                return _result(
                    terminal_result=_build_no_progress_result(
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
        return _result(continue_loop=True)

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
        return _handle_controller_refusal(
            refusal=payload_refusal,
            args_for_log=proposal_inputs,
            update_streak=True,
            allow_repair_request=True,
        )

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
        return _handle_controller_refusal(
            refusal=refusal,
            args_for_log=proposal_inputs,
            update_streak=True,
            allow_repair_request=True,
        )

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
        return _handle_controller_refusal(
            refusal=refusal,
            args_for_log=cleaned_inputs,
            update_streak=True,
            allow_repair_request=True,
        )

    step_inputs = cleaned_inputs
    inspection_refusal = _inspection_thrash_refusal(
        action_type=action_type,
        step_inputs=step_inputs,
        repeated_inspection_ref=repeated_inspection_ref,
        repeated_inspection_count=repeated_inspection_count,
    )
    if inspection_refusal is not None:
        refusal, repeat_ref = inspection_refusal
        repeated_inspection_ref = repeat_ref
        repeated_inspection_count = (repeated_inspection_count + 1) if repeat_ref else 0
        dashboard_json = started.dashboard.model_dump(mode="json")
        progress_payload = {
            "latest_refs": _latest_refs_summary(dashboard_json),
            "gap_summary": _compact_gap_summary(dashboard_json.get("gap_summary")),
            "claimability": dashboard_json.get("claimability", {}),
        }
        return _handle_controller_refusal(
            refusal=refusal,
            args_for_log=step_inputs,
            payload_extra={
                "inspection_ref": repeat_ref,
                "observed_state_labels": _progress_state_labels(progress_payload),
            },
        )
    span_open_refusal = _span_open_thrash_refusal(
        action_type=action_type,
        step_inputs=step_inputs,
        repeated_signature=repeated_span_open_signature,
        repeated_count=repeated_span_open_count,
    )
    if span_open_refusal is not None:
        refusal, repeat_signature = span_open_refusal
        repeated_span_open_signature = repeat_signature
        repeated_span_open_count = (repeated_span_open_count + 1) if repeat_signature else 0
        dashboard_json = started.dashboard.model_dump(mode="json")
        progress_payload = {
            "latest_refs": _latest_refs_summary(dashboard_json),
            "gap_summary": _compact_gap_summary(dashboard_json.get("gap_summary")),
            "claimability": dashboard_json.get("claimability", {}),
        }
        return _handle_controller_refusal(
            refusal=refusal,
            args_for_log=step_inputs,
            payload_extra={"observed_state_labels": _progress_state_labels(progress_payload)},
        )
    semantic_span_refusal = _semantic_span_repair_thrash_refusal(
        action_type=action_type,
        context_packet=context_packet,
        repeated_signature=semantic_span_repair_signature,
        repeated_count=semantic_span_repair_count,
    )
    if semantic_span_refusal is not None:
        refusal, repeat_signature = semantic_span_refusal
        semantic_span_repair_signature = repeat_signature
        semantic_span_repair_count = (semantic_span_repair_count + 1) if repeat_signature else 0
        dashboard_json = started.dashboard.model_dump(mode="json")
        progress_payload = {
            "latest_refs": _latest_refs_summary(dashboard_json),
            "gap_summary": _compact_gap_summary(dashboard_json.get("gap_summary")),
            "claimability": dashboard_json.get("claimability", {}),
        }
        return _handle_controller_refusal(
            refusal=refusal,
            args_for_log=step_inputs,
            payload_extra={"observed_state_labels": _progress_state_labels(progress_payload)},
        )
    dashboard_json = started.dashboard.model_dump(mode="json")
    redundant_step_refusal = _redundant_deterministic_step_refusal(
        action_type=action_type,
        dashboard=dashboard_json,
    )
    if redundant_step_refusal is not None:
        refusal, observed_labels = redundant_step_refusal
        progress_payload = {
            "latest_refs": _latest_refs_summary(dashboard_json),
            "gap_summary": _compact_gap_summary(dashboard_json.get("gap_summary")),
            "claimability": dashboard_json.get("claimability", {}),
        }
        return _handle_controller_refusal(
            refusal=refusal,
            args_for_log=step_inputs,
            payload_extra={
                "observed_state_labels": _progress_state_labels(progress_payload),
                "redundant_refusal_labels": observed_labels,
            },
        )
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
    result = _result(step_request=step_request, step_inputs=step_inputs)
    return StepPreparationResult(
        **{**result.__dict__, "computed_idempotency_key": computed_idempotency_key}
    )
