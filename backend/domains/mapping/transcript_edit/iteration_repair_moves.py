from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from agent_kernel.models import StepExecutionState

from .execution_action_ids import TX_APPLY_EDIT_PLAN
from agent_kernel.session import KernelSessionManager
from services.workflows.mapping.transcription_edit.persistence import TranscriptionEditPersistenceService

from .blocker_registry import apply_proposed_emergent_blocker_updates, sync_registry_from_ledger
from .contracts import TranscriptEditAgentRunRequest
from .decision_ledger import ledger_snapshot_for_payload, mark_human_resolution_ticket_state, update_ledger_from_iteration
from .decision_ledger_adapter import transcript_edit_unified_and_closure_read_from_loop_state
from .evidence_runtime import (
    cache_entry_matches_transcript,
    cache_image_verification_for_key,
    cache_span_context_for_key,
    cache_visual_evidence_for_key,
    cached_image_verification_for_key,
    cached_span_context_for_key,
    cached_visual_evidence_for_key,
    clear_cached_focus_evidence,
    coerce_artifact_ref_for_state,
    coerce_visual_evidence_state,
    evidence_request_mode_hint,
    image_verify_runtime_config,
    open_planner_context_spans_adapter,
    run_image_evidence_mode,
    selector_type_from_target,
    verify_mapping_critical_with_image_adapter,
    visual_evidence_from_verify_payload,
)
from .loop_runtime import read_step_outputs_inline, read_str
from .loop_state import TranscriptEditLoopState
from .plan_interpretation import build_apply_inputs_for_plan, max_change_class_from_plan, plan_has_review_required, plan_op_to_display_dict
from .progress_evaluation import blocking_signature, blocking_unresolved_count
from .result_policy import TranscriptEditDecision
from services.workflows.mapping.transcription_edit.run_reporting import (
    apply_result_payload,
    blocker_update_payload,
    human_feedback_needed_payload,
    image_verify_result_payload,
    open_spans_result_payload,
    plan_result_payload,
    resolver_invalid_payload,
    resolver_move_gate_payload,
    ticker_payload,
)
from .resolver_gates import accept_request_human_feedback
from .evidence_executor import execute_evidence_request, normalize_evidence_request
from .emergent_lifecycle_runtime import sync_focused_emergent_item_from_resolver_outcome
from .work_board_projection import HARNESS_EMERGENT_ITEM_PREFIX


def _transcript_edit_closure_read_ledger(state: TranscriptEditLoopState) -> dict[str, Any]:
    _, read = transcript_edit_unified_and_closure_read_from_loop_state(state)
    return read


def _continuity_delta_summary(
    *,
    move: str,
    resolver_outcome: dict[str, Any] | None,
) -> str | None:
    parts: list[str] = [f"move={move or 'unknown'}"]
    ro = resolver_outcome if isinstance(resolver_outcome, dict) else {}
    if ro.get("edit_plan"):
        parts.append("carry_edit_plan")
    if ro.get("evidence_request"):
        parts.append("carry_evidence_request")
    if ro.get("blocker_updates"):
        parts.append("carry_blocker_updates")
    if ro.get("feedback_prompt"):
        parts.append("carry_feedback_prompt")
    return "; ".join(parts)[:280] or None


def _append_continuity_step(
    state: TranscriptEditLoopState,
    *,
    focus_key: str,
    move: str,
    resolver_reason: str,
    iterations: int,
    focus_source: str | None,
    state_before_summary: dict[str, Any] | None,
    evidence_kind: str | None = None,
    state_delta_hint: str | None = None,
    continuity_supplement: dict[str, Any] | None = None,
) -> None:
    row: dict[str, Any] = {
        "decision_key": focus_key or "",
        "move": move or "unknown_move",
        "outcome": resolver_reason,
        "iteration": int(iterations),
        "focus_source": str(focus_source or "").strip()[:64] or None,
        "gate_posture": dict(state_before_summary or {}),
        "evidence_kind": str(evidence_kind).strip()[:120] if evidence_kind else None,
        "why_no_closure": str(resolver_reason or "").strip()[:280] or None,
        "state_delta_hint": str(state_delta_hint).strip()[:280] if state_delta_hint else None,
    }
    if isinstance(continuity_supplement, dict) and continuity_supplement:
        row.update(continuity_supplement)
    state.continuity_log.append(row)
    if len(state.continuity_log) > 50:
        state.continuity_log = state.continuity_log[-50:]


def _merge_last_continuity_row(state: TranscriptEditLoopState, extra: dict[str, Any]) -> None:
    if not state.continuity_log or not isinstance(extra, dict):
        return
    state.continuity_log[-1] = {**dict(state.continuity_log[-1]), **extra}


def _step_kernel_action(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    prefix: str,
    iteration: int,
    action_type: ActionType,
    inputs: dict[str, Any],
):
    from .loop_runtime import step_kernel_action

    return step_kernel_action(
        session_manager=session_manager,
        session_id=session_id,
        prefix=prefix,
        iteration=iteration,
        action_type=action_type,
        inputs=inputs,
    )


def _open_planner_context_spans(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return open_planner_context_spans_adapter(
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        top_findings=top_findings,
        step_fn=_step_kernel_action,
        read_step_outputs_inline_fn=read_step_outputs_inline,
    )


def _verify_mapping_critical_with_image(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
    source_image_refs: list[str],
    model: str,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    focus_decision_key: str | None = None,
    llm_call_seq_start: int = 0,
    validation_mode: str = "off",
) -> dict[str, Any]:
    return verify_mapping_critical_with_image_adapter(
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        top_findings=top_findings,
        source_image_refs=source_image_refs,
        model=model,
        progress_cb=progress_cb,
        focus_decision_key=focus_decision_key,
        llm_call_seq_start=llm_call_seq_start,
        validation_mode=validation_mode,
        step_fn=_step_kernel_action,
        read_step_outputs_inline_fn=read_step_outputs_inline,
        read_str_fn=read_str,
    )


def _run_image_evidence_mode(
    *,
    normalized_request: dict[str, Any],
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    source_image_refs: list[str],
    model: str,
    focus_decision_key: str | None,
    top_findings: list[dict[str, Any]],
    llm_call_seq_start: int,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    latest_visual_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    return run_image_evidence_mode(
        normalized_request=normalized_request,
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        source_image_refs=source_image_refs,
        model=model,
        focus_decision_key=focus_decision_key,
        top_findings=top_findings,
        llm_call_seq_start=llm_call_seq_start,
        progress_cb=progress_cb,
        latest_visual_evidence=latest_visual_evidence,
        step_fn=_step_kernel_action,
        read_step_outputs_inline_fn=read_step_outputs_inline,
    )


def _image_verify_runtime_config(validation_mode: str | None) -> dict[str, Any]:
    return image_verify_runtime_config(validation_mode)


def _span_to_display_dict(span: dict[str, Any]) -> dict[str, Any]:
    text = str(span.get("text") or span.get("content") or "").strip()
    return {
        "span_id": span.get("span_id"),
        "text": text[:120] + ("..." if len(text) > 120 else ""),
    }


def _cached_span_context_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> list[dict[str, Any]]:
    return cached_span_context_for_key(
        state=state,
        decision_key=decision_key,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cache_span_context_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    span_context: list[dict[str, Any]],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> None:
    cache_span_context_for_key(
        state=state,
        decision_key=decision_key,
        span_context=span_context,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cached_image_verification_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> dict[str, Any]:
    return cached_image_verification_for_key(
        state=state,
        decision_key=decision_key,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cached_visual_evidence_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> dict[str, Any]:
    return cached_visual_evidence_for_key(
        state=state,
        decision_key=decision_key,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cache_image_verification_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    image_verification: dict[str, Any],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> None:
    cache_image_verification_for_key(
        state=state,
        decision_key=decision_key,
        image_verification=image_verification,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _cache_visual_evidence_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    visual_evidence: dict[str, Any],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> None:
    cache_visual_evidence_for_key(
        state=state,
        decision_key=decision_key,
        visual_evidence=visual_evidence,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _coerce_visual_evidence_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    return coerce_visual_evidence_state(raw)


def _selector_type_from_target(target: dict[str, Any]) -> str | None:
    return selector_type_from_target(target)


def _evidence_request_mode_hint(evidence_request: dict[str, Any] | None) -> str | None:
    return evidence_request_mode_hint(evidence_request)


def _visual_evidence_from_verify_payload(
    *,
    verify_payload: dict[str, Any],
    existing_visual_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    return visual_evidence_from_verify_payload(
        verify_payload=verify_payload,
        existing_visual_evidence=existing_visual_evidence,
    )


def _coerce_artifact_ref_for_state(raw: Any) -> dict[str, Any] | None:
    return coerce_artifact_ref_for_state(raw)


def _step_story_payload(
    *,
    step_kind: str,
    why_now: str,
    trigger: str,
    state_before_summary: dict[str, Any] | None = None,
    state_delta: dict[str, Any] | None = None,
    outcome_class: str | None = None,
    next_step_rationale: str | None = None,
) -> dict[str, Any]:
    payload = {
        "step_kind": str(step_kind or "").strip().lower() or "unknown",
        "why_now": str(why_now or "").strip() or None,
        "trigger": str(trigger or "").strip() or None,
        "state_before_summary": dict(state_before_summary or {}),
        "state_delta": dict(state_delta or {}),
        "outcome_class": str(outcome_class or "").strip().lower() or None,
        "next_step_rationale": str(next_step_rationale or "").strip() or None,
    }
    return {k: v for k, v in payload.items() if v not in (None, {}, [])}


def _cache_entry_matches_transcript(
    *,
    entry: dict[str, Any],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> bool:
    return cache_entry_matches_transcript(
        entry=entry,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    )


def _clear_cached_focus_evidence(
    *,
    state: TranscriptEditLoopState,
) -> None:
    clear_cached_focus_evidence(state=state)


def handle_repair_move_outcome(
    *,
    state: TranscriptEditLoopState,
    request: TranscriptEditAgentRunRequest,
    tx_persistence: TranscriptionEditPersistenceService,
    session_manager: KernelSessionManager,
    session_id: str,
    iterations: int,
    focus_key: str,
    focus_source: str | None,
    move: str,
    resolver_reason: str,
    resolver_outcome: dict[str, Any] | None,
    answered_ticket: dict[str, Any] | None,
    focus_feedback: dict[str, Any] | None,
    planning_findings: list[dict[str, Any]],
    source_transcript_hash: str,
    model: str,
    validation_mode: str,
    active_ticket_snapshot: dict[str, Any] | None,
    visual_evidence: dict[str, Any],
    image_verification: dict[str, Any],
    evidence_attempts_counts: dict[str, int],
    raw_output_excerpt: str,
    blocker_posture: dict[str, Any] | None,
    emit_progress_fn: Callable[[Callable[[dict[str, Any]], None] | None, dict[str, Any]], None],
    progress_cb: Callable[[dict[str, Any]], None] | None,
    append_blocker_iteration_recap_fn: Callable[..., None],
    emit_ticket_lifecycle_transition_fn: Callable[..., None],
    set_pending_feedback_prompt_fn: Callable[..., None],
    build_feedback_prompt_fn: Callable[..., dict[str, Any] | None],
    accept_mark_blocked_fn: Callable[..., bool],
    accept_mark_resolved_no_edit_fn: Callable[..., bool],
    accept_apply_edit_plan_fn: Callable[..., bool],
    findings_for_focus_key_fn: Callable[..., list[dict[str, Any]]],
    extract_validation_error_class_fn: Callable[[str], str | None],
    ticket_lifecycle_snapshot_for_key_fn: Callable[..., list[dict[str, Any]]],
    latest_human_resolution_ticket_fn: Callable[..., dict[str, Any] | None],
    registry_row_for_decision_key_fn: Callable[..., dict[str, Any] | None],
) -> TranscriptEditDecision | None:
    signals = blocker_posture if isinstance(blocker_posture, dict) else {}
    if isinstance(resolver_outcome, dict):
        _it_u = resolver_outcome.get("iteration_understanding")
        if isinstance(_it_u, dict) and _it_u:
            from .llm_startup_understanding import apply_llm_iteration_updates_to_ledger_and_registry

            _ms_it: dict[str, Any] = {}
            state.decision_ledger, state.blocker_registry = apply_llm_iteration_updates_to_ledger_and_registry(
                ledger=state.decision_ledger,
                registry=state.blocker_registry,
                iteration_payload=_it_u,
                merge_stats=_ms_it,
                fallback_decision_key=str(focus_key or "").strip().lower() or None,
            )
            if isinstance(state.decision_ledger.get("llm_iteration_understanding"), dict):
                state.llm_iteration_understanding = dict(state.decision_ledger["llm_iteration_understanding"])
    state_before_summary = {
        "understanding_strength": str(signals.get("understanding_strength") or "unknown").strip().lower() or "unknown",
        "needs_orientation": bool(signals.get("needs_orientation")),
        "needs_inventory": bool(signals.get("needs_inventory")),
        "has_fresh_signal": bool(signals.get("has_fresh_signal")),
        "cached_context_present": bool(signals.get("cached_context_present")),
        "repeat_without_signal": bool(signals.get("repeat_without_signal")),
        "generic_board_mapping_signal": signals.get("generic_board_mapping_signal"),
        "generic_board_materiality": signals.get("generic_board_materiality"),
    }
    _sd_hint = _continuity_delta_summary(
        move=move,
        resolver_outcome=resolver_outcome if isinstance(resolver_outcome, dict) else None,
    )
    _append_continuity_step(
        state,
        focus_key=focus_key,
        move=move,
        resolver_reason=resolver_reason,
        iterations=iterations,
        focus_source=focus_source,
        state_before_summary=state_before_summary,
        state_delta_hint=_sd_hint,
    )
    board_sync = sync_focused_emergent_item_from_resolver_outcome(
        state,
        focus_key=focus_key,
        move=move,
        resolver_outcome=resolver_outcome if isinstance(resolver_outcome, dict) else None,
        policy_signals=policy_signals,
        now_epoch=int(time.time()),
    )
    if isinstance(board_sync, dict):
        state.last_board_observability = dict(board_sync)
        prev_hint = str((state.continuity_log[-1] or {}).get("state_delta_hint") or "").strip()
        step_hint = (
            f"resolution_lifecycle:{board_sync.get('state_before')}→{board_sync.get('state_after')}"
        )[:260]
        _merge_last_continuity_row(
            state,
            {
                "resolution_progress": dict(board_sync),
                "state_delta_hint": f"{prev_hint}; {step_hint}".strip("; ")
                if prev_hint
                else step_hint,
            },
        )
    if move == "propose_blocker_updates":
        blocker_updates = (
            resolver_outcome.get("blocker_updates")
            if isinstance(resolver_outcome, dict) and isinstance(resolver_outcome.get("blocker_updates"), list)
            else []
        )
        apply_result = apply_proposed_emergent_blocker_updates(
            registry=state.blocker_registry,
            blocker_updates=[row for row in blocker_updates if isinstance(row, dict)],
            fallback_decision_key=focus_key,
        )
        state.blocker_registry = (
            dict(apply_result.get("registry"))
            if isinstance(apply_result.get("registry"), dict)
            else state.blocker_registry
        )
        accepted = [row for row in list(apply_result.get("accepted") or []) if isinstance(row, dict)]
        rejected = [row for row in list(apply_result.get("rejected") or []) if isinstance(row, dict)]
        emit_progress_fn(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="blocker_update",
                message=f"Processed emergent blocker proposals: accepted={len(accepted)}, rejected={len(rejected)}.",
                latest_refs=state.latest_refs,
                detail={"accepted_count": len(accepted), "rejected_count": len(rejected), "move": "propose_blocker_updates"},
            ),
        )
        for row in accepted[:12]:
            emit_progress_fn(
                progress_cb,
                blocker_update_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    status="accepted",
                    operation=str(row.get("operation") or "").strip().lower() or None,
                    blocker_id=str(row.get("blocker_id") or "").strip() or None,
                    blocker_kind=str(row.get("blocker_kind") or "").strip().lower() or None,
                    blocking_class=str(row.get("blocking_class") or "").strip().lower() or None,
                    reason=resolver_reason,
                    step_story=_step_story_payload(
                        step_kind="blocker_promotion",
                        why_now="The case identified a new explicit blocker surface.",
                        trigger="propose_blocker_updates",
                        state_before_summary=state_before_summary,
                        state_delta={"accepted_count": len(accepted), "rejected_count": len(rejected)},
                        outcome_class="accepted" if accepted else "rejected",
                        next_step_rationale="Use the updated blocker surface to select the next bounded action.",
                    ),
                ),
            )
        for row in rejected[:12]:
            emit_progress_fn(
                progress_cb,
                blocker_update_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    status="rejected",
                    operation=str(row.get("operation") or "").strip().lower() or None,
                    blocker_id=str(row.get("blocker_id") or "").strip() or None,
                    blocker_kind=None,
                    blocking_class=None,
                    reason=str(row.get("reason") or "").strip() or "unknown_rejection",
                    step_story=_step_story_payload(
                        step_kind="blocker_promotion",
                        why_now="The blocker proposal did not satisfy runtime policy.",
                        trigger="propose_blocker_updates",
                        state_before_summary=state_before_summary,
                        state_delta={"accepted_count": len(accepted), "rejected_count": len(rejected)},
                        outcome_class="rejected",
                        next_step_rationale="Return to the support state or a narrower investigation move.",
                    ),
                ),
            )
        if accepted:
            state.evidence_signal_counter += 1
            state.no_progress_streak = 0
            state.last_progress_reason = "emergent_blocker_update_accepted"
            append_blocker_iteration_recap_fn(
                action_attempted="propose_blocker_updates",
                result="accepted",
                decision_key=focus_key,
                reason=resolver_reason,
            )
            return None
        state.last_reason = "tx_agent_blocker_update_rejected"
        append_blocker_iteration_recap_fn(
            action_attempted="propose_blocker_updates",
            result="rejected",
            decision_key=focus_key,
            reason=resolver_reason,
        )
        return None
    if move == "propose_work_board_changes":
        from .work_board_runtime import apply_work_board_changes_from_resolver

        raw_changes = (
            resolver_outcome.get("work_board_changes")
            if isinstance(resolver_outcome, dict) and isinstance(resolver_outcome.get("work_board_changes"), list)
            else []
        )
        apply_result = apply_work_board_changes_from_resolver(
            state=state,
            decision_ledger=state.decision_ledger,
            work_board_changes=[dict(x) for x in raw_changes if isinstance(x, dict)],
        )
        accepted = [dict(x) for x in list(apply_result.get("accepted") or []) if isinstance(x, dict)]
        rejected = [dict(x) for x in list(apply_result.get("rejected") or []) if isinstance(x, dict)]
        _merge_last_continuity_row(
            state,
            {
                "work_board_emergence_audit": {
                    "accepted": accepted[:12],
                    "rejected": rejected[:12],
                }
            },
        )
        emit_progress_fn(
            progress_cb,
            ticker_payload(
                iteration=iterations,
                phase="work_board_emergence",
                message=f"Work board change proposals processed: accepted={len(accepted)}, rejected={len(rejected)}.",
                latest_refs=state.latest_refs,
                detail={
                    "accepted_count": len(accepted),
                    "rejected_count": len(rejected),
                    "move": "propose_work_board_changes",
                },
            ),
        )
        if accepted:
            promo = next((a for a in accepted if str(a.get("op")) == "add_item"), None)
            attach = next((a for a in accepted if str(a.get("op")) == "attach_note"), None)
            if isinstance(promo, dict) and str(promo.get("item_id") or "").strip():
                tid = str(promo.get("item_id")).strip()
                bp: dict[str, Any] = {
                    "event": "emergent_promoted",
                    "focus_target_kind": "harness_emergent",
                    "item_id": tid,
                    "state_before": None,
                    "state_after": "open",
                    "transition_reason": "promoted_from_resolver_work_board_changes",
                    "newly_promoted": True,
                    "recently_touched": True,
                    "recency_rank": 0,
                }
                state.last_board_observability = bp
                _merge_last_continuity_row(
                    state,
                    {
                        "resolution_progress": bp,
                        "state_delta_hint": f"resolution_promoted:{tid[:64]}",
                    },
                )
            elif isinstance(attach, dict) and str(attach.get("target_item_id") or "").strip():
                tid = str(attach.get("target_item_id")).strip()
                bp2: dict[str, Any] = {
                    "event": "context_note_attached",
                    "focus_target_kind": (
                        "harness_emergent" if tid.startswith(HARNESS_EMERGENT_ITEM_PREFIX) else "ledger_decision"
                    ),
                    "item_id": tid,
                    "transition_reason": "attach_note_from_resolver_work_board_changes",
                    "recently_touched": True,
                }
                state.last_board_observability = bp2
                _merge_last_continuity_row(
                    state,
                    {
                        "resolution_progress": bp2,
                        "state_delta_hint": f"resolution_note_attached:{tid[:64]}",
                    },
                )
            state.evidence_signal_counter += 1
            state.no_progress_streak = 0
            state.last_progress_reason = "work_board_emergence_accepted"
            append_blocker_iteration_recap_fn(
                action_attempted="propose_work_board_changes",
                result="accepted",
                decision_key=focus_key,
                reason=resolver_reason,
            )
            return None
        state.last_reason = "tx_agent_work_board_changes_rejected"
        append_blocker_iteration_recap_fn(
            action_attempted="propose_work_board_changes",
            result="rejected",
            decision_key=focus_key,
            reason=resolver_reason,
        )
        return None
    if move == "request_human_feedback":
        if not accept_request_human_feedback(policy_signals=signals, hitl_enabled=request.hitl_enabled):
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="rejected",
                    gate_reason="escalation_not_yet_eligible",
                    ticket_snapshot=active_ticket_snapshot,
                    step_story=_step_story_payload(
                        step_kind="human_feedback",
                        why_now="Escalation is not yet justified because the case still lacks fresh narrowing signal.",
                        trigger="request_human_feedback",
                        state_before_summary=state_before_summary,
                        state_delta={"gate_outcome": "rejected"},
                        outcome_class="discouraged",
                        next_step_rationale="Continue orientation, inventory, or targeted verification until fresh signal narrows the case.",
                    ),
                ),
            )
            append_blocker_iteration_recap_fn(
                action_attempted="request_hitl",
                result="rejected",
                decision_key=focus_key,
                reason="escalation_not_yet_eligible",
            )
            state.last_reason = "tx_agent_request_hitl_rejected"
            return None
        emit_progress_fn(
            progress_cb,
            resolver_move_gate_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                decision_key=focus_key,
                move=move,
                gate_outcome="accepted",
                gate_reason="accepted_request_human_feedback",
                ticket_snapshot=active_ticket_snapshot,
                step_story=_step_story_payload(
                    step_kind="human_feedback",
                    why_now="The case is sufficiently narrow and materially unresolved, and the freshness posture supports bounded HITL.",
                    trigger="request_human_feedback",
                    state_before_summary=state_before_summary,
                    state_delta={"gate_outcome": "accepted"},
                    outcome_class="accepted",
                    next_step_rationale="Wait for operator input and integrate it explicitly on the next iteration against the current freshness posture.",
                ),
            ),
        )
        if not state.pending_feedback_prompt_id and request.hitl_enabled:
            resolver_prompt = (
                dict(resolver_outcome.get("feedback_prompt"))
                if isinstance(resolver_outcome, dict) and isinstance(resolver_outcome.get("feedback_prompt"), dict)
                else {}
            )
            feedback_prompt = None
            if resolver_prompt:
                feedback_prompt = {
                    "prompt_id": f"hitl_{focus_key}_{iterations}_resolver",
                    "line1": str(resolver_prompt.get("line1") or "").strip() or "Human feedback needed.",
                    "line2": str(resolver_prompt.get("line2") or "").strip() or "Please choose the best-supported option.",
                    "choices": [str(v).strip() for v in list(resolver_prompt.get("choices") or []) if str(v).strip()][:6],
                    "default_choice": None,
                    "context": {"decision_key": focus_key or None},
                }
                if feedback_prompt["choices"]:
                    feedback_prompt["default_choice"] = feedback_prompt["choices"][0]
            if feedback_prompt is None:
                feedback_prompt = build_feedback_prompt_fn(
                    state=state,
                    iterations=iterations,
                    image_verification=image_verification,
                    visual_evidence=visual_evidence,
                )
            if feedback_prompt is not None:
                emit_progress_fn(
                    progress_cb,
                    human_feedback_needed_payload(
                        iteration=iterations,
                        latest_refs=state.latest_refs,
                        feedback_prompt=feedback_prompt,
                        evidence_attempts=evidence_attempts_counts,
                    ),
                )
                set_pending_feedback_prompt_fn(
                    feedback_prompt=feedback_prompt,
                    decision_key=str((feedback_prompt.get("context") or {}).get("decision_key") or "").strip().lower(),
                    supersession_reason="resolver_requested_feedback",
                )
        state.last_reason = "tx_agent_closure_requirements_unresolved"
        append_blocker_iteration_recap_fn(
            action_attempted="request_hitl",
            result="waiting_feedback",
            decision_key=focus_key,
            reason=resolver_reason,
        )
        return None

    if move == "mark_blocked":
        if resolver_reason.startswith(("resolver_move_invalid:", "resolver_plan_invalid:")):
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="retrying" if state.invalid_plan_strikes + 1 < request.max_invalid_plan_attempts else "blocked",
                    gate_reason="resolver_invalid_payload",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
        if not accept_mark_blocked_fn(
            decision_ledger=_transcript_edit_closure_read_ledger(state),
            decision_key=focus_key,
            resolver_reason=resolver_reason,
            hitl_enabled=request.hitl_enabled,
            policy_signals=signals,
        ):
            state.last_reason = f"mark_blocked_rejected:{resolver_reason}"
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="rejected",
                    gate_reason="mark_blocked_rejected_by_runtime_gate",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
            append_blocker_iteration_recap_fn(action_attempted="mark_blocked", result="rejected", decision_key=focus_key, reason=resolver_reason)
            return None
        if not resolver_reason.startswith(("resolver_move_invalid:", "resolver_plan_invalid:")):
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="accepted",
                    gate_reason=(
                        "blocked_no_safe_integration_after_feedback"
                        if resolver_reason.startswith("blocked_no_safe_integration_after_feedback")
                        else "accepted_mark_blocked"
                    ),
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
        if resolver_reason.startswith(("resolver_move_invalid:", "resolver_plan_invalid:")):
            reason_suffix = resolver_reason
            if reason_suffix.startswith("resolver_move_invalid:"):
                reason_suffix = reason_suffix.replace("resolver_move_invalid:", "", 1)
            if reason_suffix.startswith("resolver_plan_invalid:"):
                reason_suffix = reason_suffix.replace("resolver_plan_invalid:", "", 1)
            state.invalid_plan_strikes += 1
            exhausted = state.invalid_plan_strikes >= request.max_invalid_plan_attempts
            post_feedback_ticket_state = (
                str((resolver_outcome or {}).get("post_feedback_ticket_state") or "").strip().lower()
                if isinstance(resolver_outcome, dict)
                else ""
            ) or ("answered_unintegrated" if isinstance(answered_ticket, dict) else None)
            post_feedback_ticket_id = (
                str((resolver_outcome or {}).get("post_feedback_ticket_id") or "").strip()
                if isinstance(resolver_outcome, dict)
                else ""
            ) or (str((answered_ticket or {}).get("ticket_id") or "").strip() if isinstance(answered_ticket, dict) else None)
            validation_error_class = extract_validation_error_class_fn(reason_suffix)
            emit_progress_fn(
                progress_cb,
                resolver_invalid_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    reason=reason_suffix,
                    invalid_plan_strikes=state.invalid_plan_strikes,
                    max_invalid_plan_attempts=request.max_invalid_plan_attempts,
                    exhausted=exhausted,
                    decision_key=focus_key,
                    post_feedback_ticket_state=post_feedback_ticket_state,
                    post_feedback_ticket_id=post_feedback_ticket_id,
                    validation_error_class=validation_error_class,
                    raw_output_excerpt=raw_output_excerpt,
                ),
            )
            if exhausted:
                if post_feedback_ticket_state in {"answered_unintegrated", "integration_attempted_failed"}:
                    if post_feedback_ticket_id:
                        state.decision_ledger = mark_human_resolution_ticket_state(
                            ledger=state.decision_ledger,
                            ticket_id=post_feedback_ticket_id,
                            decision_key=focus_key,
                            lifecycle_state="integration_attempted_failed",
                            relevance="active",
                        )
                    emit_ticket_lifecycle_transition_fn(
                        ticket_id=post_feedback_ticket_id,
                        decision_key=focus_key,
                        lifecycle_state="integration_attempted_failed",
                        relevance="active",
                        reason="resolver_invalid_exhausted",
                    )
                return TranscriptEditDecision(
                    status="needs_review",
                    reason_code=(
                        f"tx_agent_post_feedback_resolver_invalid_exhausted:{reason_suffix}"
                        if post_feedback_ticket_state in {"answered_unintegrated", "integration_attempted_failed"}
                        else f"tx_agent_plan_invalid_exhausted:{reason_suffix}"
                    ),
                    review_required=True,
                )
            state.last_reason = f"tx_agent_plan_invalid_retrying:{reason_suffix}"
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="retrying",
                    gate_reason="resolver_invalid_retry_budget_remaining",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
            return None
        return TranscriptEditDecision(
            status="needs_review",
            reason_code=(
                "tx_agent_consistent_feedback_no_safe_plan"
                if resolver_reason.startswith("blocked_no_safe_integration_after_feedback")
                else "tx_agent_closure_requirements_unresolved"
            ),
            review_required=True,
        )
    if move == "mark_resolved_no_edit":
        if accept_mark_resolved_no_edit_fn(
            decision_ledger=_transcript_edit_closure_read_ledger(state),
            decision_key=focus_key,
        ):
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="accepted",
                    gate_reason="accepted_mark_resolved_no_edit",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
            state.last_reason = resolver_reason
            return None
        state.last_reason = f"mark_resolved_no_edit_rejected:{resolver_reason}"
        emit_progress_fn(
            progress_cb,
            resolver_move_gate_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                decision_key=focus_key,
                move=move,
                gate_outcome="rejected",
                gate_reason="mark_resolved_no_edit_rejected_by_runtime_gate",
                ticket_snapshot=active_ticket_snapshot,
            ),
        )
        return None
    if move == "gather_more_evidence":
        evidence_request = (
            resolver_outcome.get("evidence_request")
            if isinstance(resolver_outcome, dict) and isinstance(resolver_outcome.get("evidence_request"), dict)
            else None
        )
        if bool(signals.get("repeat_without_signal")):
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="rejected",
                    gate_reason="repeat_without_signal_discouraged",
                    ticket_snapshot=active_ticket_snapshot,
                    step_story=_step_story_payload(
                        step_kind="evidence",
                        why_now="Cached context is present, but no fresh signal was added, so repeating evidence work is discouraged.",
                        trigger="gather_more_evidence",
                        state_before_summary=state_before_summary,
                        state_delta={"gate_outcome": "rejected"},
                        outcome_class="discouraged",
                        next_step_rationale="Shift to a different evidence lane, a focus reframe, or a blocker update that would create fresh signal.",
                    ),
                ),
            )
            append_blocker_iteration_recap_fn(
                action_attempted="gather_more_evidence",
                result="rejected",
                decision_key=focus_key,
                reason="repeat_without_signal_discouraged",
            )
            state.last_reason = "gather_more_evidence_rejected:repeat_without_signal"
            return None
        normalized_request, normalize_reason = normalize_evidence_request(
            evidence_request=evidence_request,
            decision_key=focus_key,
        )
        if normalized_request is None:
            evidence_kind = str((evidence_request or {}).get("kind") or "").strip().lower() or None
            evidence_mode = _evidence_request_mode_hint(evidence_request)
            state.last_reason = f"gather_more_evidence_rejected:{normalize_reason}"
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="rejected",
                    gate_reason="invalid_evidence_request",
                    ticket_snapshot=active_ticket_snapshot,
                    normalize_reason=normalize_reason,
                    evidence_request_kind=evidence_kind,
                    evidence_request_mode=evidence_mode,
                ),
            )
            return None
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="accepted",
                    gate_reason=f"accepted_new_evidence_kind:{str(normalized_request.get('kind') or '')}",
                    ticket_snapshot=active_ticket_snapshot,
                    step_story=_step_story_payload(
                        step_kind="evidence",
                        why_now="The current case posture still needs a bounded evidence move, and the cached context is not yet enough on its own.",
                        trigger="gather_more_evidence",
                        state_before_summary=state_before_summary,
                        state_delta={"gate_outcome": "accepted"},
                        outcome_class="accepted",
                        next_step_rationale="Use the evidence result to decide whether fresh signal is still needed or whether the case is now narrow.",
                    ),
                ),
            )
        focused_findings = findings_for_focus_key_fn(top_findings=planning_findings, focus_key=focus_key)
        focus_findings = focused_findings if focused_findings else planning_findings
        evidence_result = execute_evidence_request(
            normalized_request=normalized_request,
            source_transcript_hash=source_transcript_hash,
            repeat_guard=state.evidence_repeat_guard,
            evidence_signal_counter=state.evidence_signal_counter,
            max_repeats_per_signature=2,
            open_spans_runner=lambda _req: _open_planner_context_spans(
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=state.current_transcript_ref or "",
                top_findings=focus_findings,
            ),
            image_verify_runner=lambda _req: _verify_mapping_critical_with_image(
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=state.current_transcript_ref or "",
                top_findings=focus_findings,
                source_image_refs=request.source_image_refs,
                model=model,
                progress_cb=progress_cb,
                focus_decision_key=focus_key,
                llm_call_seq_start=state.llm_call_seq,
                validation_mode=validation_mode,
            ),
            image_evidence_runner=lambda _req: _run_image_evidence_mode(
                normalized_request=_req,
                session_manager=session_manager,
                session_id=session_id,
                iteration=iterations,
                dossier_id=request.dossier_id,
                source_transcript_ref=state.current_transcript_ref or "",
                source_image_refs=request.source_image_refs,
                model=model,
                focus_decision_key=focus_key,
                top_findings=focus_findings,
                llm_call_seq_start=state.llm_call_seq,
                progress_cb=progress_cb,
                latest_visual_evidence=visual_evidence,
            ),
            retrieve_dependency_runner=None,
        )
        _ek = f"{str(evidence_result.get('kind') or '')}:{str(evidence_result.get('mode') or '')}".rstrip(":")
        _ev_st = str(evidence_result.get("status") or "").strip().lower()
        _g_delta = f"gather_more_evidence; status={_ev_st or 'n/a'}; kind={_ek or 'n/a'}"
        _append_continuity_step(
            state,
            focus_key=focus_key,
            move="gather_more_evidence",
            resolver_reason=str(evidence_result.get("reason") or "evidence_result_unknown"),
            iterations=iterations,
            focus_source=focus_source,
            state_before_summary=state_before_summary,
            evidence_kind=_ek or None,
            state_delta_hint=_g_delta,
        )
        if str(evidence_result.get("status") or "") == "repeat_blocked":
            emit_progress_fn(
                progress_cb,
                resolver_move_gate_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    decision_key=focus_key,
                    move=move,
                    gate_outcome="blocked",
                    gate_reason="rejected_repeated_evidence_after_binding_feedback",
                    ticket_snapshot=active_ticket_snapshot,
                ),
            )
            return TranscriptEditDecision(
                status="needs_review",
                reason_code="tx_agent_evidence_repeat_budget_exhausted",
                review_required=True,
            )
        if str(evidence_result.get("status") or "") in {"unsupported", "invalid"}:
            state.last_reason = f"gather_more_evidence_failed:{evidence_result.get('reason')}"
            return None
        extra_spans = evidence_result.get("span_context") if isinstance(evidence_result.get("span_context"), list) else []
        if extra_spans:
            span_context = [s for s in extra_spans if isinstance(s, dict)]
            _cache_span_context_for_key(
                state=state,
                decision_key=focus_key,
                span_context=span_context,
                source_transcript_ref=state.current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
            )
            state.evidence_signal_counter += 1
            emit_progress_fn(
                progress_cb,
                open_spans_result_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    spans_display=[_span_to_display_dict(s) for s in span_context[:6]],
                ),
            )
        extra_image_evidence = (
            evidence_result.get("image_evidence")
            if isinstance(evidence_result.get("image_evidence"), dict)
            else {}
        )
        if extra_image_evidence:
            visual_evidence = _coerce_visual_evidence_state(extra_image_evidence)
            _cache_visual_evidence_for_key(
                state=state,
                decision_key=focus_key,
                visual_evidence=visual_evidence,
                source_transcript_ref=state.current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
            )
            state.latest_refs = (
                dict(extra_image_evidence.get("latest_refs"))
                if isinstance(extra_image_evidence.get("latest_refs"), dict)
                else state.latest_refs
            )
            state.llm_call_seq = int(extra_image_evidence.get("llm_call_seq_end") or state.llm_call_seq)
            mode = str(extra_image_evidence.get("mode") or "").strip().lower() or "unknown"
            emit_progress_fn(
                progress_cb,
                ticker_payload(
                    iteration=iterations,
                    phase="image_verify",
                    message=f"Image evidence {mode} completed for {focus_key}.",
                    latest_refs=state.latest_refs,
                    detail={
                        "evidence_kind": "image_evidence",
                        "mode": mode,
                        "decision_key": focus_key,
                        "tx_image_evidence_region_ref": visual_evidence.get("tx_image_evidence_region_ref"),
                        "tx_image_evidence_context_ref": visual_evidence.get("tx_image_evidence_context_ref"),
                        "locator_status": str((visual_evidence.get("locator") or {}).get("status") or ""),
                        "selector_type": visual_evidence.get("selector_type"),
                        "crop_box": visual_evidence.get("crop_box"),
                        "zoom_factor": visual_evidence.get("zoom_factor"),
                        "region_lineage": (
                            dict(visual_evidence.get("region_lineage"))
                            if isinstance(visual_evidence.get("region_lineage"), dict)
                            else {}
                        ),
                    },
                ),
            )
        extra_image_verification = evidence_result.get("image_verification") if isinstance(evidence_result.get("image_verification"), dict) else {}
        if extra_image_verification:
            image_verification = extra_image_verification
            _cache_image_verification_for_key(
                state=state,
                decision_key=focus_key,
                image_verification=image_verification,
                source_transcript_ref=state.current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
            )
            state.llm_call_seq = int(image_verification.get("llm_call_seq_end") or state.llm_call_seq)
            state.latest_refs = image_verification.get("latest_refs", state.latest_refs)
            iv_payload = image_verification.get("payload") if isinstance(image_verification.get("payload"), dict) else {}
            if iv_payload:
                merged_visual = _visual_evidence_from_verify_payload(
                    verify_payload=iv_payload,
                    existing_visual_evidence=visual_evidence,
                )
                if merged_visual:
                    visual_evidence = merged_visual
                    _cache_visual_evidence_for_key(
                        state=state,
                        decision_key=focus_key,
                        visual_evidence=visual_evidence,
                        source_transcript_ref=state.current_transcript_ref,
                        source_transcript_hash=source_transcript_hash,
                    )
            iv_results = iv_payload.get("results") if isinstance(iv_payload, dict) else []
            iv_results = iv_results if isinstance(iv_results, list) else []
            _, read_before_iv = transcript_edit_unified_and_closure_read_from_loop_state(state)
            before_sig = blocking_signature(read_before_iv)
            state.decision_ledger = update_ledger_from_iteration(
                ledger=state.decision_ledger,
                findings=[],
                image_results=[result for result in iv_results if isinstance(result, dict)],
            )
            _, read_after_iv = transcript_edit_unified_and_closure_read_from_loop_state(state)
            state.blocker_registry = sync_registry_from_ledger(
                registry=state.blocker_registry,
                decision_ledger=read_after_iv,
                source_transcript_ref=state.current_transcript_ref,
            )
            after_sig = blocking_signature(read_after_iv)
            if iv_results and before_sig != after_sig:
                state.evidence_signal_counter += 1
            emit_progress_fn(
                progress_cb,
                image_verify_result_payload(
                    iteration=iterations,
                    latest_refs=state.latest_refs,
                    iv_payload=iv_payload,
                    iv_results=[r for r in iv_results[:8] if isinstance(r, dict)],
                    iv_confirmed=sum(1 for r in iv_results if isinstance(r, dict) and str(r.get("status") or "").lower() in {"confirmed", "match"}),
                    iv_rejected=sum(1 for r in iv_results if isinstance(r, dict) and str(r.get("status") or "").lower() in {"rejected", "mismatch"}),
                    iv_total=len(iv_results),
                    decision_ledger=ledger_snapshot_for_payload(state.decision_ledger),
                    decision_key=focus_key,
                    llm_call_seq_end=state.llm_call_seq,
                    diagnostics=[],
                ),
            )
        state.last_reason = resolver_reason
        return None

    manual_plan = (resolver_outcome.get("edit_plan") if isinstance(resolver_outcome, dict) else None) if move == "apply_edit_plan" else None
    if manual_plan is None:
        manual_plan = request.edit_plan if isinstance(request.edit_plan, dict) else None
    if manual_plan is not None:
        if not accept_apply_edit_plan_fn(
            resolver_decision_key=focus_key,
            focus_key=focus_key,
            plan_payload=manual_plan,
            policy_signals=signals,
        ):
            state.invalid_plan_strikes += 1
            if state.invalid_plan_strikes >= request.max_invalid_plan_attempts:
                emit_progress_fn(
                    progress_cb,
                    resolver_move_gate_payload(
                        iteration=iterations,
                        latest_refs=state.latest_refs,
                        decision_key=focus_key,
                        move="apply_edit_plan",
                        gate_outcome="rejected",
                        gate_reason="apply_scope_mismatch",
                        ticket_snapshot=active_ticket_snapshot,
                        step_story=_step_story_payload(
                            step_kind="repair",
                            why_now="The proposed repair does not match the current focus posture, including its freshness posture.",
                            trigger="apply_edit_plan",
                            state_before_summary=state_before_summary,
                            state_delta={"gate_outcome": "rejected"},
                            outcome_class="discouraged",
                            next_step_rationale="Return to investigation or narrower focus selection until the posture is fresh enough for repair.",
                        ),
                    ),
                )
                return TranscriptEditDecision(
                    status="needs_review",
                    reason_code=(
                        "tx_agent_plan_invalid:weak_understanding"
                        if str(signals.get("understanding_strength") or "").strip().lower() == "weak"
                        else "tx_agent_plan_invalid:focus_scope_mismatch"
                    ),
                    review_required=True,
                )
            return None
        selected_plan_payload = manual_plan
        plan_reason = "resolver_edit_plan" if move == "apply_edit_plan" else "manual_plan"
        emit_progress_fn(
            progress_cb,
            resolver_move_gate_payload(
                iteration=iterations,
                latest_refs=state.latest_refs,
                decision_key=focus_key,
                move="apply_edit_plan",
                gate_outcome="accepted",
                gate_reason="accepted_apply_for_answered_ticket" if isinstance(answered_ticket, dict) else "accepted_apply_edit_plan",
                ticket_snapshot=active_ticket_snapshot,
                step_story=_step_story_payload(
                    step_kind="repair",
                    why_now="The case is narrow enough for direct repair, and fresh signal supports a bounded edit.",
                    trigger="apply_edit_plan",
                    state_before_summary=state_before_summary,
                    state_delta={"gate_outcome": "accepted"},
                    outcome_class="accepted",
                    next_step_rationale="Re-audit the transcript and observe whether the fresh edit improved closure.",
                ),
            ),
        )
    else:
        state.invalid_plan_strikes += 1
        if state.invalid_plan_strikes >= request.max_invalid_plan_attempts:
            return TranscriptEditDecision(
                status="needs_review",
                reason_code="tx_agent_plan_invalid:missing_apply_edit_plan",
                review_required=True,
            )
        return None
    plan_ops = selected_plan_payload.get("ops") if isinstance(selected_plan_payload, dict) else []
    plan_ops = plan_ops if isinstance(plan_ops, list) else []
    emit_progress_fn(
        progress_cb,
        plan_result_payload(
            iteration=iterations,
            latest_refs=state.latest_refs,
            plan_reason=plan_reason,
            op_count=len(plan_ops),
            ops_preview=[plan_op_to_display_dict(op) for op in plan_ops[:6] if isinstance(op, dict)],
            ticket_lifecycle_snapshot=ticket_lifecycle_snapshot_for_key_fn(
                decision_ledger=_transcript_edit_closure_read_ledger(state),
                decision_key=focus_key,
            ),
            step_story=_step_story_payload(
                step_kind="repair",
                why_now="The resolver produced a bounded plan that passed runtime gates, with fresh signal still supporting the repair posture.",
                trigger="apply_edit_plan",
                state_before_summary=state_before_summary,
                state_delta={"plan_op_count": len(plan_ops)},
                outcome_class="accepted",
                next_step_rationale="Apply the plan and then re-audit for closure change against the current freshness posture.",
            ),
        ),
    )
    apply = _step_kernel_action(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_apply",
        iteration=iterations,
        action_type=TX_APPLY_EDIT_PLAN,
        inputs=build_apply_inputs_for_plan(
            persistence=tx_persistence,
            dossier_id=request.dossier_id,
            plan_payload=selected_plan_payload,
        ),
    )
    state.latest_refs = apply.dashboard.latest_refs.model_dump(mode="json")
    emit_progress_fn(
        progress_cb,
        apply_result_payload(
            iteration=iterations,
            latest_refs=state.latest_refs,
            execution_state=str(apply.execution_state.value),
            plan_op_count=len(plan_ops),
            ops_display=[plan_op_to_display_dict(op) for op in plan_ops[:6] if isinstance(op, dict)],
            step_story=_step_story_payload(
                step_kind="repair_apply",
                why_now="The runtime is applying the bounded plan to the transcript, reusing cached context only as support.",
                trigger="tx_apply_edit_plan",
                state_before_summary=state_before_summary,
                state_delta={"execution_state": str(apply.execution_state.value)},
                outcome_class="accepted" if apply.execution_state == StepExecutionState.EXECUTED else "rejected",
                next_step_rationale="Re-audit the edited transcript and update durable state from the result instead of trusting cached context alone.",
            ),
        ),
    )
    if apply.execution_state != StepExecutionState.EXECUTED:
        reason = apply.refusal.reason_code if apply.refusal is not None else "tx_apply_refused"
        return TranscriptEditDecision(status="needs_review", reason_code=reason, review_required=True)
    apply_inline = read_step_outputs_inline(apply.step_record)
    edited_ref = read_str(apply_inline.get("tx_edited_transcript_ref"))
    if edited_ref:
        prior_ref = str(state.current_transcript_ref or "").strip()
        next_ref = str(edited_ref).strip()
        if next_ref and next_ref != prior_ref:
            _clear_cached_focus_evidence(state=state)
        state.current_transcript_ref = edited_ref
    plan_cc = max_change_class_from_plan(selected_plan_payload or {})
    if plan_cc in {"semantic", "structural"}:
        state.applied_non_normalization = True
    if plan_has_review_required(selected_plan_payload or {}):
        state.applied_requires_review = True
    if len(plan_ops) > 0:
        state.applied_any_edits = True
        state.pending_reaudit_after_apply = True
        read_for_reaudit = _transcript_edit_closure_read_ledger(state)
        state.apply_reaudit_baseline_blocking_count = blocking_unresolved_count(read_for_reaudit)
        state.apply_reaudit_baseline_blocking_signature = blocking_signature(read_for_reaudit)
        ticket_prompt_id = str((focus_feedback or {}).get("prompt_id") or "").strip() if isinstance(focus_feedback, dict) else ""
        ticket_decision_key = (
            str((focus_feedback or {}).get("decision_key") or "").strip().lower()
            if isinstance(focus_feedback, dict)
            else str(focus_key or "").strip().lower()
        )
        if not ticket_prompt_id:
            answered_ticket = latest_human_resolution_ticket_fn(
                decision_ledger=read_for_reaudit,
                decision_key=ticket_decision_key,
                lifecycle_states={"answered_unintegrated", "integration_attempted_failed"},
            )
            ticket_prompt_id = str((answered_ticket or {}).get("ticket_id") or "").strip()
            ticket_decision_key = str((answered_ticket or {}).get("decision_key") or ticket_decision_key).strip().lower()
        if ticket_prompt_id and ticket_decision_key:
            state.decision_ledger = mark_human_resolution_ticket_state(
                ledger=state.decision_ledger,
                ticket_id=ticket_prompt_id,
                decision_key=ticket_decision_key,
                lifecycle_state="integrated",
                integrated=True,
                relevance="inactive",
            )
            emit_ticket_lifecycle_transition_fn(
                ticket_id=ticket_prompt_id,
                decision_key=ticket_decision_key,
                lifecycle_state="integrated",
                relevance="inactive",
                reason="apply_edit_plan",
            )
        read_after_ticket = _transcript_edit_closure_read_ledger(state)
        state.blocker_registry = sync_registry_from_ledger(
            registry=state.blocker_registry,
            decision_ledger=read_after_ticket,
            source_transcript_ref=state.current_transcript_ref,
        )
        remaining_for_focus = registry_row_for_decision_key_fn(registry=state.blocker_registry, decision_key=focus_key)
        outcome_code = (
            "feedback_integrated_blocker_still_open"
            if isinstance(remaining_for_focus, dict)
            and str(remaining_for_focus.get("state") or "").strip().lower() in {"open", "waiting_feedback", "answered_unintegrated"}
            else "feedback_integrated_blocker_cleared"
        )
        append_blocker_iteration_recap_fn(
            action_attempted="integrate_feedback",
            result=outcome_code,
            decision_key=focus_key,
            reason="apply_edit_plan",
        )
    state.invalid_plan_strikes = 0
    state.last_reason = "tx_apply_completed_waiting_reaudit"
    return None


__all__ = [
    "_open_planner_context_spans",
    "_verify_mapping_critical_with_image",
    "_run_image_evidence_mode",
    "_image_verify_runtime_config",
    "_span_to_display_dict",
    "_cached_span_context_for_key",
    "_cache_span_context_for_key",
    "_cached_image_verification_for_key",
    "_cached_visual_evidence_for_key",
    "_cache_image_verification_for_key",
    "_cache_visual_evidence_for_key",
    "_coerce_visual_evidence_state",
    "_selector_type_from_target",
    "_evidence_request_mode_hint",
    "_visual_evidence_from_verify_payload",
    "_coerce_artifact_ref_for_state",
    "_cache_entry_matches_transcript",
    "_clear_cached_focus_evidence",
]



